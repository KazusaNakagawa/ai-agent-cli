import json
import logging

from src.local_llm.briefing import PrefetchedContext
from src.local_llm.portfolio import (
    GENERATION_ERROR_TOPIC,
    MAX_ROW_CONTENT_CHARS,
    NO_NEWS_TOPIC,
    PORTFOLIO_ROW_FORMAT,
    build_row_prompt,
    generate_portfolio_table,
    render_numbered_hits,
)
from src.local_llm.search import SearchResult


class _ScriptedOllama:
    """ticker ごとに固定の JSON 応答を返す structured-output スタブ。"""

    def __init__(self, replies: dict[str, dict | str]):
        self.replies = replies  # ticker → dict (json.dumps される) or 生文字列
        self.calls: list[dict] = []

    def chat(self, *, model, messages, options=None, format=None):
        self.calls.append(
            {
                "model": model,
                "messages": list(messages),
                "options": options,
                "format": format,
            }
        )
        prompt = messages[-1]["content"]
        for ticker, reply in self.replies.items():
            if f"対象銘柄: {ticker}" in prompt:
                content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
                return {"message": {"content": content}}
        return {"message": {"content": "{}"}}


def _ctx(per_ticker: dict[str, list[SearchResult]]) -> PrefetchedContext:
    return PrefetchedContext(
        macro=[], per_ticker=per_ticker, geo_by_topic={}, events_by_name={}
    )


_PLTR_HITS = [
    SearchResult("PLTR wins Army deal", "https://e.com/p1", "a $480M contract"),
    SearchResult("PLTR | analyst view", "https://e.com/p2", "price target $145"),
]


# ---------------------------------------------------------------------------
# render_numbered_hits / build_row_prompt
# ---------------------------------------------------------------------------


def test_render_numbered_hits_numbers_hits_and_omits_urls():
    block = render_numbered_hits(_PLTR_HITS)

    assert block.splitlines()[0].startswith("1. PLTR wins Army deal")
    assert "2. PLTR | analyst view" in block
    # URL はモデルに見せない — 番号引用 + Python 側解決が捏造を構造的に防ぐ
    assert "https://" not in block


def test_render_numbered_hits_includes_article_content_when_present():
    hits = [
        SearchResult("T", "https://e.com/1", "desc", content="本文 $480M 契約")
    ]
    block = render_numbered_hits(hits)
    assert "本文抜粋: 本文 $480M 契約" in block
    assert "https://" not in block


def test_render_numbered_hits_truncates_long_article_content():
    hits = [
        SearchResult("T", "https://e.com/1", "desc", content="x" * 5000)
    ]
    block = render_numbered_hits(hits)
    content_line = [l for l in block.splitlines() if "本文抜粋" in l][0]
    # 1 行トピック抽出タスクに全文 (1800 字) は不要 — 行プロンプトでは短く切る
    assert len(content_line) < MAX_ROW_CONTENT_CHARS + 50
    assert content_line.endswith("...")


def test_build_row_prompt_contains_ticker_and_hits():
    out = build_row_prompt("PLTR", _PLTR_HITS, today="2026-06-13")
    assert "対象銘柄: PLTR" in out
    assert "2026-06-13" in out
    assert "1. PLTR wins Army deal" in out
    assert "source_index" in out


# ---------------------------------------------------------------------------
# generate_portfolio_table
# ---------------------------------------------------------------------------


def test_generate_portfolio_table_resolves_index_to_url_in_python():
    olm = _ScriptedOllama(
        {"PLTR": {"topic": "米陸軍と$480M契約を締結", "source_index": 1}}
    )

    table = generate_portfolio_table(
        ["PLTR"],
        ctx=_ctx({"PLTR": _PLTR_HITS}),
        moves={"PLTR": "↑3.2%  ($128.12)"},
        ollama_client=olm,
        model="m",
        options={"num_ctx": 16384},
        today="2026-06-13",
    )

    assert "## 保有銘柄テーブル" in table
    assert "|---|---|---|---|" in table
    assert "| PLTR | ↑3.2%  ($128.12) | 米陸軍と$480M契約を締結 | [PLTR wins Army deal](https://e.com/p1) |" in table
    # structured outputs の schema と options が chat() に渡る
    assert olm.calls[0]["format"] == PORTFOLIO_ROW_FORMAT
    assert olm.calls[0]["options"] == {"num_ctx": 16384}


def test_generate_portfolio_table_skips_llm_when_no_hits():
    olm = _ScriptedOllama({})

    table = generate_portfolio_table(
        ["MSFT"],
        ctx=_ctx({"MSFT": []}),
        moves={"MSFT": "↓0.5%  ($387.71)"},
        ollama_client=olm,
        model="m",
        today="2026-06-13",
    )

    assert olm.calls == []  # ヒット 0 件は LLM を呼ばない
    assert f"| MSFT | ↓0.5%  ($387.71) | {NO_NEWS_TOPIC} | - |" in table


def test_generate_portfolio_table_out_of_range_index_means_no_source(caplog):
    olm = _ScriptedOllama({"PLTR": {"topic": "話題", "source_index": 99}})

    with caplog.at_level(logging.WARNING, logger="src.local_llm.portfolio"):
        table = generate_portfolio_table(
            ["PLTR"],
            ctx=_ctx({"PLTR": _PLTR_HITS}),
            moves={"PLTR": "↑1.0%"},
            ollama_client=olm,
            model="m",
            today="2026-06-13",
        )

    assert "| PLTR | ↑1.0% | 話題 | - |" in table
    assert any("out of range" in r.message for r in caplog.records)


def test_generate_portfolio_table_null_index_means_no_source():
    olm = _ScriptedOllama({"PLTR": {"topic": NO_NEWS_TOPIC, "source_index": None}})

    table = generate_portfolio_table(
        ["PLTR"],
        ctx=_ctx({"PLTR": _PLTR_HITS}),
        moves={"PLTR": "↑1.0%"},
        ollama_client=olm,
        model="m",
        today="2026-06-13",
    )

    assert f"| PLTR | ↑1.0% | {NO_NEWS_TOPIC} | - |" in table


def test_generate_portfolio_table_invalid_json_falls_back(caplog):
    olm = _ScriptedOllama({"PLTR": "これは JSON ではない"})

    with caplog.at_level(logging.WARNING, logger="src.local_llm.portfolio"):
        table = generate_portfolio_table(
            ["PLTR"],
            ctx=_ctx({"PLTR": _PLTR_HITS}),
            moves={"PLTR": "↑1.0%"},
            ollama_client=olm,
            model="m",
            today="2026-06-13",
        )

    assert f"| PLTR | ↑1.0% | {GENERATION_ERROR_TOPIC} | - |" in table
    assert any("JSON parse failed" in r.message for r in caplog.records)


def test_generate_portfolio_table_sanitizes_pipes_in_topic_and_title():
    olm = _ScriptedOllama(
        {"PLTR": {"topic": "契約 | 拡大", "source_index": 2}}  # hit 2 のタイトルに | を含む
    )

    table = generate_portfolio_table(
        ["PLTR"],
        ctx=_ctx({"PLTR": _PLTR_HITS}),
        moves={"PLTR": "↑1.0%"},
        ollama_client=olm,
        model="m",
        today="2026-06-13",
    )

    row = [l for l in table.splitlines() if l.startswith("| PLTR")][0]
    # セルは 4 列 (縦棒 5 本) を維持 — topic / title 内の | は空白に置換される
    assert row.count("|") == 5
    assert "PLTR   analyst view" in row


def test_generate_portfolio_table_sanitizes_newlines_in_cells():
    olm = _ScriptedOllama(
        {"PLTR": {"topic": "契約\n拡大", "source_index": 1}}  # topic に改行
    )

    table = generate_portfolio_table(
        ["PLTR"],
        ctx=_ctx({"PLTR": _PLTR_HITS}),
        moves={"PLTR": "↑1.0%\n続伸"},  # 値動きにも改行
        ollama_client=olm,
        model="m",
        today="2026-06-13",
    )

    row = [l for l in table.splitlines() if l.startswith("| PLTR")][0]
    # 改行は空白に畳まれ、行は 4 列 (縦棒 5 本) のまま
    assert "\n" not in row
    assert row.count("|") == 5
    assert "契約 拡大" in row
    assert "↑1.0% 続伸" in row


def test_generate_portfolio_table_covers_all_tickers_independently():
    olm = _ScriptedOllama(
        {
            "PLTR": {"topic": "PLTR の話題", "source_index": 1},
            "NVDA": {"topic": "NVDA の話題", "source_index": 1},
        }
    )
    nvda_hits = [SearchResult("NVDA China", "https://e.com/n1", "export licence")]

    table = generate_portfolio_table(
        ["PLTR", "NVDA", "MSFT"],
        ctx=_ctx({"PLTR": _PLTR_HITS, "NVDA": nvda_hits, "MSFT": []}),
        moves={"PLTR": "↑1.0%", "NVDA": "↓2.0%", "MSFT": "-"},
        ollama_client=olm,
        model="m",
        today="2026-06-13",
    )

    # 行ごとに自銘柄の検索結果だけが出典になる (混線が構造的に起きない)
    assert "| PLTR | ↑1.0% | PLTR の話題 | [PLTR wins Army deal](https://e.com/p1) |" in table
    assert "| NVDA | ↓2.0% | NVDA の話題 | [NVDA China](https://e.com/n1) |" in table
    assert f"| MSFT | - | {NO_NEWS_TOPIC} | - |" in table
    # 各コールには対象銘柄のヒットしか渡っていない
    for call in olm.calls:
        prompt = call["messages"][-1]["content"]
        if "対象銘柄: PLTR" in prompt:
            assert "NVDA China" not in prompt
        if "対象銘柄: NVDA" in prompt:
            assert "PLTR wins Army deal" not in prompt
