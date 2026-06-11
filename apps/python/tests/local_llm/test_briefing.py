import logging
from datetime import datetime
from pathlib import Path

import pytest

from src.config import (
    BriefingConfig,
    Conflict,
    GeopoliticalConfig,
    PortfolioConfig,
    WatchSector,
)
from src.local_llm import cli
from src.local_llm.briefing import (
    PrefetchedContext,
    UrlValidation,
    build_section_geo_events_prompt,
    build_section_insight_prompt,
    build_section_portfolio_prompt,
    build_section_topnews_prompt,
    collect_references,
    compose_briefing_md,
    ensure_portfolio_table_header,
    generate_local_briefing,
    load_local_briefing_system_prompt,
    prefetch_briefing_context,
    render_geo_events_block,
    render_macro_block,
    render_portfolio_block,
    render_prefetch_debug_block,
    summarize_prefetch_hits,
    validate_urls,
)
from src.local_llm.search import BraveSearchError, SearchResult


def _minimal_cfg(
    tickers: list[str] | None = None,
    conflicts: list[Conflict] | None = None,
) -> BriefingConfig:
    return BriefingConfig(
        portfolio=PortfolioConfig(
            tickers=tickers or ["PLTR", "NVDA"], themes=["AI", "半導体"]
        ),
        watch_sectors=[WatchSector(sector="AI & Cloud", tickers=["NVDA"])],
        geopolitical=GeopoliticalConfig(conflicts=conflicts or []),
        watch_events=[],
        discord_token="",
        discord_channel_id="",
        notion_api_key="",
        notion_database_id="",
    )


# ---------------------------------------------------------------------------
# Pre-fetch
# ---------------------------------------------------------------------------


class _StubSearch:
    """Returns canned hits per query; records calls."""

    def __init__(self, responses: dict[str, list[SearchResult]] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []

    def search(self, query, count=5):
        self.calls.append({"query": query, "count": count})
        return self.responses.get(query, [])


def test_prefetch_searches_every_ticker_plus_macro_plus_geo():
    cfg = _minimal_cfg(
        tickers=["PLTR", "MSFT", "GOOGL"],
        conflicts=[
            Conflict(name="米中技術覇権争い", affected_sectors=["半導体"]),
            Conflict(name="中東・ホルムズ封鎖", affected_sectors=["エネルギー"]),
        ],
    )
    pltr_hit = SearchResult("PLTR Q2", "https://e.com/pltr", "earnings beat")
    macro_hit = SearchResult("Markets", "https://e.com/mkt", "rally")
    geo_hit_1 = SearchResult("China chips", "https://e.com/geo1", "export rules")
    geo_hit_2 = SearchResult("Hormuz", "https://e.com/geo2", "tanker")
    search = _StubSearch(
        responses={
            "stock market news 2026-06-09": [macro_hit],
            "PLTR stock news 2026-06-09": [pltr_hit],
            "MSFT stock news 2026-06-09": [],
            "GOOGL stock news 2026-06-09": [],
            "米中技術覇権争い today": [geo_hit_1],
            "中東・ホルムズ封鎖 today": [geo_hit_2],
        }
    )

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    # Every ticker AND every conflict was searched, even if 0 hits
    queried = [c["query"] for c in search.calls]
    assert "stock market news 2026-06-09" in queried
    assert "PLTR stock news 2026-06-09" in queried
    assert "MSFT stock news 2026-06-09" in queried
    assert "GOOGL stock news 2026-06-09" in queried
    assert "米中技術覇権争い today" in queried
    assert "中東・ホルムズ封鎖 today" in queried

    assert ctx.macro == [macro_hit]
    assert ctx.per_ticker["PLTR"] == [pltr_hit]
    assert ctx.per_ticker["MSFT"] == []
    assert ctx.per_ticker["GOOGL"] == []
    assert ctx.geo_by_topic["米中技術覇権争い"] == [geo_hit_1]
    assert ctx.geo_by_topic["中東・ホルムズ封鎖"] == [geo_hit_2]
    assert ctx.events_by_name == {}


def test_prefetch_handles_brave_errors_per_query(caplog):
    cfg = _minimal_cfg(tickers=["PLTR"])

    class _FailingSearch:
        def __init__(self):
            self.calls: list[str] = []

        def search(self, query, count=5):
            self.calls.append(query)
            if "PLTR" in query:
                raise BraveSearchError("HTTP 429: rate limited")
            return []

    search = _FailingSearch()
    with caplog.at_level(logging.WARNING, logger="src.local_llm.briefing"):
        ctx = prefetch_briefing_context(
            cfg, search_client=search, today="2026-06-09"
        )
    # Failure on the PLTR query did not abort the whole pre-fetch
    assert "stock market news 2026-06-09" in search.calls
    assert "PLTR stock news 2026-06-09" in search.calls
    assert ctx.per_ticker["PLTR"] == []
    assert any("PLTR stock news 2026-06-09" in r.message for r in caplog.records)


def test_prefetch_skips_geo_when_no_conflicts_configured():
    cfg = _minimal_cfg(tickers=["PLTR"], conflicts=[])
    search = _StubSearch()

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    assert ctx.geo_by_topic == {}
    assert ctx.events_by_name == {}
    queried = [c["query"] for c in search.calls]
    geo_or_event_queries = [
        q for q in queried
        if "today" in q and q != "stock market news 2026-06-09" and "stock news" not in q
    ]
    assert geo_or_event_queries == []


def _full_ctx() -> PrefetchedContext:
    return PrefetchedContext(
        macro=[SearchResult("M", "https://e.com/m", "d")],
        per_ticker={
            "PLTR": [SearchResult("P", "https://e.com/p", "dp")],
            "MSFT": [],
        },
        geo_by_topic={
            "米中": [SearchResult("G", "https://e.com/g", "dg")],
        },
        events_by_name={
            "Fed FOMC": [SearchResult("E", "https://e.com/e", "de")],
        },
    )


def test_render_macro_block_only_contains_macro_hits():
    block = render_macro_block(_full_ctx())
    assert "マクロ・市場全体" in block
    assert "https://e.com/m" in block
    # 銘柄・地政学・イベントは出ない (各セクション専用ブロックなので)
    assert "PLTR" not in block
    assert "地政学" not in block
    assert "監視イベント" not in block


def test_render_portfolio_block_only_contains_ticker_hits():
    block = render_portfolio_block(_full_ctx())
    assert "### 銘柄別検索結果" in block
    assert "**PLTR**" in block and "https://e.com/p" in block
    assert "**MSFT**" in block and "(検索ヒットなし)" in block
    assert "マクロ" not in block
    assert "地政学" not in block


def test_render_geo_events_block_contains_both_sections():
    block = render_geo_events_block(_full_ctx())
    assert "### 地政学トピック" in block
    assert "**米中**" in block and "https://e.com/g" in block
    assert "### 監視イベント" in block
    assert "**Fed FOMC**" in block and "https://e.com/e" in block


def test_render_geo_events_block_empty_when_both_missing():
    ctx = PrefetchedContext(
        macro=[], per_ticker={}, geo_by_topic={}, events_by_name={}
    )
    assert render_geo_events_block(ctx) == ""


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def test_build_section_topnews_prompt_only_passes_macro_hits():
    ctx = _full_ctx()
    out = build_section_topnews_prompt(ctx, today="2026-06-09")
    assert "今日のトップニュース" in out
    assert "2026-06-09" in out
    assert "## 検索結果" in out
    assert "https://e.com/m" in out
    # 銘柄・地政学のブロックはこの段では渡さない
    assert "PLTR" not in out
    assert "地政学" not in out


def test_build_section_portfolio_prompt_only_passes_ticker_hits():
    cfg = _minimal_cfg(tickers=["PLTR", "MSFT"])
    ctx = _full_ctx()
    out = build_section_portfolio_prompt(
        cfg, stocks="PLTR +2.1%\nMSFT -1.3%", today="2026-06-09", ctx=ctx
    )
    assert "保有銘柄テーブル" in out
    assert "PLTR" in out and "MSFT" in out
    assert "PLTR +2.1%" in out
    assert "https://e.com/p" in out
    # マクロ・地政学・イベントの URL はこの段では渡さない
    assert "https://e.com/m" not in out
    assert "https://e.com/g" not in out


def test_build_section_geo_events_prompt_only_passes_geo_events():
    cfg = _minimal_cfg(tickers=["PLTR", "NVDA"])
    ctx = _full_ctx()
    out = build_section_geo_events_prompt(cfg, ctx=ctx, today="2026-06-09")
    assert "地政学トピック" in out
    assert "監視イベント" in out
    assert "https://e.com/g" in out
    assert "https://e.com/e" in out
    # tickers は影響判定用に渡る (本文には PLTR / NVDA が出る)
    assert "PLTR" in out
    assert "NVDA" in out
    # 銘柄の URL ブロックは渡さない
    assert "https://e.com/p" not in out
    # マクロ URL も渡さない
    assert "https://e.com/m" not in out


def test_summarize_prefetch_hits_lists_all_buckets_with_counts():
    ctx = PrefetchedContext(
        macro=[SearchResult("m1", "https://e.com/m", "")],
        per_ticker={
            "PLTR": [SearchResult("p", "https://e.com/p", "")],
            "MSFT": [],
        },
        geo_by_topic={
            "米中": [
                SearchResult("g1", "https://e.com/g1", ""),
                SearchResult("g2", "https://e.com/g2", ""),
            ],
        },
        events_by_name={"FOMC": []},
    )
    out = summarize_prefetch_hits(ctx)
    assert "macro=1" in out
    assert "PLTR:1" in out
    assert "MSFT:0" in out
    assert "米中:2" in out
    assert "FOMC:0" in out


def test_summarize_prefetch_hits_drops_empty_categories():
    ctx = PrefetchedContext(
        macro=[], per_ticker={}, geo_by_topic={}, events_by_name={}
    )
    out = summarize_prefetch_hits(ctx)
    assert out == "macro=0"
    assert "tickers" not in out
    assert "geo" not in out
    assert "events" not in out


def test_render_prefetch_debug_block_includes_all_urls_inside_details():
    ctx = PrefetchedContext(
        macro=[SearchResult("M1", "https://e.com/m", "")],
        per_ticker={
            "PLTR": [SearchResult("P1", "https://e.com/p", "")],
            "MSFT": [],
        },
        geo_by_topic={"米中": [SearchResult("G1", "https://e.com/g", "")]},
        events_by_name={"FOMC": [SearchResult("E1", "https://e.com/e", "")]},
    )
    block = render_prefetch_debug_block(ctx)
    assert block.startswith("<details>")
    assert block.rstrip().endswith("</details>")
    assert "Pre-fetch raw" in block
    # 全 URL が含まれる
    assert "https://e.com/m" in block
    assert "https://e.com/p" in block
    assert "https://e.com/g" in block
    assert "https://e.com/e" in block
    # 0 件のセクションは「検索ヒットなし」と明記
    assert "**MSFT (0 件)**" in block
    assert "(検索ヒットなし)" in block


def test_compose_briefing_md_includes_prefetch_summary_line():
    md = compose_briefing_md(
        body="b",
        model="qwen2.5:14b",
        generated_at=datetime(2026, 6, 9, 9, 15, 0),
        prefetch_summary="macro=3 / tickers=[PLTR:3, MSFT:0]",
    )
    assert "Brave hits: macro=3 / tickers=[PLTR:3, MSFT:0]" in md


def test_ensure_portfolio_table_header_prepends_when_divider_missing():
    body = (
        "| PLTR | ↓0.9% | (確認できず) | - |\n"
        "| NVDA | ↑1.2% | 新型 GPU 発表 | [Bloomberg](https://e.com/n) |\n"
    )
    out = ensure_portfolio_table_header(body)
    assert out.startswith("## 保有銘柄テーブル")
    assert "| 銘柄 | 値動き | 今日のトピック (1 行) | 出典 |" in out
    assert "|---|---|---|---|" in out
    # データ行は保持される
    assert "| PLTR | ↓0.9% |" in out
    assert "| NVDA | ↑1.2% |" in out


def test_ensure_portfolio_table_header_noop_when_divider_present():
    body = (
        "## 保有銘柄テーブル\n\n"
        "| 銘柄 | 値動き | 今日のトピック | 出典 |\n"
        "|---|---|---|---|\n"
        "| PLTR | ↓0.9% | 何か | - |\n"
    )
    assert ensure_portfolio_table_header(body) == body


def test_ensure_portfolio_table_header_noop_when_no_table():
    body = "本文だけでテーブル要素なし\n"
    assert ensure_portfolio_table_header(body) == body


def test_ensure_portfolio_table_header_inserts_divider_only_when_header_present():
    body = (
        "## 保有銘柄テーブル\n\n"
        "| 銘柄 | 値動き | 今日のトピック (1 行) | 出典 |\n"
        "| PLTR | ↓0.9% | (確認できず) | - |\n"
    )
    out = ensure_portfolio_table_header(body)
    # Header line should appear exactly once (no duplication)
    assert out.count("| 銘柄 | 値動き | 今日のトピック (1 行) | 出典 |") == 1
    assert "|---|---|---|---|" in out
    assert "| PLTR | ↓0.9% |" in out


def test_build_section_insight_prompt_carries_prior_text_and_themes():
    cfg = _minimal_cfg()
    out = build_section_insight_prompt(
        cfg, prior_text="### マクロ\n本文", today="2026-06-09"
    )
    assert "自分への示唆" in out
    assert "AI" in out  # themes
    assert "本文" in out


def test_system_prompt_carries_citation_rules():
    sys_prompt = load_local_briefing_system_prompt()
    assert "検索結果" in sys_prompt
    # No-tool-call mode: the system prompt should NOT instruct the model to call web_search
    assert "web_search" not in sys_prompt


# ---------------------------------------------------------------------------
# generate_local_briefing — single-turn
# ---------------------------------------------------------------------------


class _ScriptedOllama:
    def __init__(self, reply: dict):
        self._reply = reply
        self.calls: list[dict] = []

    def chat(self, *, model, messages):
        self.calls.append({"model": model, "messages": list(messages)})
        return self._reply


def test_generate_local_briefing_is_single_turn_with_system_prompt(capsys):
    olm = _ScriptedOllama(reply={"message": {"content": "### 出力\nbody"}})

    out = generate_local_briefing(
        "PROMPT",
        ollama_client=olm,
        model="qwen2.5:14b",
        system_prompt="SYS",
    )

    assert out == "### 出力\nbody"
    assert len(olm.calls) == 1
    assert olm.calls[0]["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "PROMPT"},
    ]
    assert "### 出力" in capsys.readouterr().out


def test_generate_local_briefing_omits_system_when_not_provided():
    olm = _ScriptedOllama(reply={"message": {"content": "body"}})
    out = generate_local_briefing(
        "PROMPT", ollama_client=olm, model="m"
    )
    assert out == "body"
    assert olm.calls[0]["messages"] == [{"role": "user", "content": "PROMPT"}]


# ---------------------------------------------------------------------------
# compose_briefing_md
# ---------------------------------------------------------------------------


def test_compose_briefing_md_emits_caveat_then_body():
    md = compose_briefing_md(
        body="### 今日のサマリー\n本文\n",
        model="qwen2.5:14b",
        generated_at=datetime(2026, 6, 9, 9, 15, 0),
    )

    head, _, body = md.partition("\n\n---\n\n")
    assert "ローカル LLM" in head
    assert "qwen2.5:14b" in head
    assert "pre-fetch" in head
    assert "2026-06-09T09:15:00" in head
    assert body.startswith("### 今日のサマリー")


def test_compose_briefing_md_renders_url_validation_line():
    md = compose_briefing_md(
        body="b",
        model="m",
        generated_at=datetime(2026, 6, 9, 9, 15, 0),
        url_validation=UrlValidation(body="b", total=5, fabricated=2),
    )
    assert "URL 検証: 3/5" in md
    assert "捏造 2 件" in md


# ---------------------------------------------------------------------------
# URL post-validation
# ---------------------------------------------------------------------------


def _ctx_with_urls(*urls: str) -> PrefetchedContext:
    return PrefetchedContext(
        macro=[SearchResult(f"t{i}", u, "d") for i, u in enumerate(urls)],
        per_ticker={},
        geo_by_topic={},
        events_by_name={},
    )


def test_validate_urls_passes_through_allowed_urls():
    ctx = _ctx_with_urls("https://e.com/a", "https://e.com/b")
    body = "本文 [A](https://e.com/a) と [B](https://e.com/b) を引用。"

    v = validate_urls(body, ctx)

    assert v.total == 2
    assert v.fabricated == 0
    assert v.verified == 2
    assert v.body == body  # untouched


def test_validate_urls_replaces_fabricated_with_marker():
    ctx = _ctx_with_urls("https://e.com/real")
    body = "[real](https://e.com/real) と [fake](https://finance.yahoo.com/quote/PLTR/) を含む。"

    v = validate_urls(body, ctx)

    assert v.total == 2
    assert v.fabricated == 1
    assert "https://e.com/real" in v.body
    assert "https://finance.yahoo.com/quote/PLTR/" not in v.body
    assert "<URL未検証>" in v.body


def test_validate_urls_handles_zero_urls():
    ctx = _ctx_with_urls("https://e.com/a")
    v = validate_urls("URL のない本文。", ctx)
    assert v.total == 0 and v.fabricated == 0 and v.verified == 0


def test_validate_urls_handles_bare_urls_without_markdown():
    ctx = _ctx_with_urls("https://e.com/a")
    body = "リンク: https://e.com/a と捏造の https://fake.example.com/x"
    v = validate_urls(body, ctx)
    assert v.total == 2
    assert v.fabricated == 1
    assert "<URL未検証>" in v.body
    assert "https://e.com/a" in v.body


def test_validate_urls_collects_from_all_prefetch_buckets():
    ctx = PrefetchedContext(
        macro=[SearchResult("m", "https://e.com/macro", "")],
        per_ticker={"PLTR": [SearchResult("p", "https://e.com/pltr", "")]},
        geo_by_topic={"x": [SearchResult("g", "https://e.com/geo", "")]},
        events_by_name={"e": [SearchResult("ev", "https://e.com/ev", "")]},
    )
    body = (
        "[m](https://e.com/macro) [p](https://e.com/pltr) "
        "[g](https://e.com/geo) [ev](https://e.com/ev)"
    )
    v = validate_urls(body, ctx)
    assert v.fabricated == 0
    assert v.verified == 4


def test_compose_briefing_md_search_disabled_caveat():
    md = compose_briefing_md(
        body="body",
        model="qwen2.5:14b",
        generated_at=datetime(2026, 6, 9, 9, 15, 0),
        search_enabled=False,
    )
    assert "BRAVE_API_KEY 未設定" in md


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class _FakeRunCLI:
    """Helper for cli._cmd_briefing tests: monkeypatches collaborators."""

    def __init__(self, monkeypatch, tmp_path, *, briefing_text="### 今日\nbody\n"):
        self.notion_calls: list[dict] = []
        self.output_dir = tmp_path / "out"
        self.output_dir.mkdir()
        self.search_clients: list = []
        self.prefetch_calls: list[dict] = []
        self.generate_calls: list[dict] = []

        monkeypatch.setenv("BRAVE_API_KEY", "test-brave-key")
        monkeypatch.setattr(cli, "BRIEFING_OUTPUT_DIR", self.output_dir)
        monkeypatch.setattr(cli, "fetch_stock_moves", lambda tickers: "PLTR +1%")
        monkeypatch.setattr(cli, "load_briefing_config", lambda: _minimal_cfg())
        monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
        monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)

        def _fake_prefetch(cfg, *, search_client, today):
            self.search_clients.append(search_client)
            self.prefetch_calls.append({"today": today, "tickers": list(cfg.portfolio.tickers)})
            return PrefetchedContext(
                macro=[],
                per_ticker={t: [] for t in cfg.portfolio.tickers},
                geo_by_topic={},
                events_by_name={},
            )

        monkeypatch.setattr(cli, "prefetch_briefing_context", _fake_prefetch)
        monkeypatch.setattr(
            cli,
            "build_section_topnews_prompt",
            lambda ctx, *, today: f"PROMPT_TOP(today={today})",
        )
        monkeypatch.setattr(
            cli,
            "build_section_portfolio_prompt",
            lambda cfg, *, stocks, today, ctx: (
                f"PROMPT_PORT(today={today}, stocks={stocks})"
            ),
        )
        monkeypatch.setattr(
            cli,
            "build_section_geo_events_prompt",
            lambda cfg, *, ctx, today: f"PROMPT_GEO(today={today})",
        )
        monkeypatch.setattr(
            cli,
            "build_section_insight_prompt",
            lambda cfg, *, prior_text, today: (
                f"PROMPT_INS(today={today}, prior={prior_text})"
            ),
        )
        monkeypatch.setattr(
            cli, "collect_references", lambda ctx, body: "## 参考記事\n- (stub)"
        )
        monkeypatch.setattr(
            cli, "load_local_briefing_system_prompt", lambda: "SYS"
        )

        def _fake_generate(prompt, *, ollama_client, model, system_prompt):
            self.generate_calls.append(
                {"prompt": prompt, "system_prompt": system_prompt}
            )
            # CLI 側は 4 回 chat() を呼ぶ。テストごとに変えたい本文 (URL 捏造を
            # 仕込む等) は 1 段目 (topnews) に集約し、他はラベルだけ返す。
            if "PROMPT_TOP" in prompt:
                return briefing_text
            if "PROMPT_PORT" in prompt:
                # わざと見出し + ヘッダ + 区切り行を省略して、CLI 側の補強関数で
                # 復元されることを下のテストで検証する。
                return "| PLTR | ↓0.9% | (確認できず) | - |"
            if "PROMPT_GEO" in prompt:
                return "## 地政学トピック"
            if "PROMPT_INS" in prompt:
                return "## 自分への示唆"
            return ""

        monkeypatch.setattr(cli, "generate_local_briefing", _fake_generate)

        def _fake_notion(text, api_key, db_id, *, title, tags=None, extra_properties=None):
            self.notion_calls.append({"text": text, "title": title, "tags": tags})
            return "https://www.notion.so/fake"

        monkeypatch.setattr(cli, "send_to_notion", _fake_notion)


def _cfg_with_notion() -> BriefingConfig:
    return _minimal_cfg().model_copy(
        update={"notion_api_key": "k", "notion_database_id": "d"}
    )


def test_cmd_briefing_prefetches_and_writes_local_file(monkeypatch, tmp_path):
    fake = _FakeRunCLI(monkeypatch, tmp_path)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    files = list(fake.output_dir.glob("local_*.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "ローカル LLM" in content
    assert "### 今日" in content  # topnews segment from briefing_text
    # Pre-fetch ran with the search client + tickers from briefing.json
    assert len(fake.prefetch_calls) == 1
    assert fake.prefetch_calls[0]["tickers"] == ["PLTR", "NVDA"]
    assert len(fake.search_clients) == 1
    # 4 段の chat() が順番に呼ばれている
    assert len(fake.generate_calls) == 4
    prompts = [c["prompt"] for c in fake.generate_calls]
    assert "PROMPT_TOP" in prompts[0]
    assert "PROMPT_PORT" in prompts[1]
    assert "PROMPT_GEO" in prompts[2]
    assert "PROMPT_INS" in prompts[3]
    # insight 段には先行 3 段の本文が prior_text として渡る
    assert "保有銘柄テーブル" in prompts[3]
    # 全段に同じ system prompt が乗る
    assert all(c["system_prompt"] == "SYS" for c in fake.generate_calls)
    # 参考記事セクションが Python 側で追加されている
    assert "## 参考記事" in content
    # portfolio セグメントはモデルが見出し・区切り行を省略したが、CLI 側の
    # ensure_portfolio_table_header で復元されている
    assert "## 保有銘柄テーブル" in content
    assert "|---|---|---|---|" in content
    # URL 検証行が caveat に入っている (今回は本文に URL なし → 0/0)
    assert "URL 検証" in content
    # 取得件数サマリと折りたたみデバッグブロックが透明性のために含まれる
    assert "Brave hits" in content
    assert "<details>" in content
    assert "Pre-fetch raw" in content
    assert fake.notion_calls == []


def test_cmd_briefing_strips_fabricated_urls_from_output(monkeypatch, tmp_path, caplog):
    fake = _FakeRunCLI(
        monkeypatch,
        tmp_path,
        briefing_text="### 今日\n[fake](https://fabricated.example.com/x)\n",
    )

    with caplog.at_level(logging.WARNING, logger="src.local_llm.cli"):
        rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    files = list(fake.output_dir.glob("local_*.md"))
    assert len(files) == 1
    content = files[0].read_text()
    # 捏造 URL は本文から除去されている
    assert "https://fabricated.example.com" not in content
    assert "<URL未検証>" in content
    # caveat にも捏造件数が出ている
    assert "捏造 1 件" in content
    assert any("URL 捏造検出" in r.message for r in caplog.records)


def test_cmd_briefing_posts_to_notion_when_flag(monkeypatch, tmp_path):
    fake = _FakeRunCLI(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "load_briefing_config", _cfg_with_notion)

    rc = cli.main(["--briefing", "--notion", "--root", str(tmp_path)])

    assert rc == 0
    assert len(fake.notion_calls) == 1
    call = fake.notion_calls[0]
    assert "ローカルブリーフィング" in call["title"]
    assert "local" in (call["tags"] or [])
    assert "agent" in (call["tags"] or [])


def test_cmd_briefing_notion_without_flag_is_noop(monkeypatch, tmp_path):
    fake = _FakeRunCLI(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "load_briefing_config", _cfg_with_notion)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    assert fake.notion_calls == []


def test_cmd_briefing_without_brave_api_key_fails_fast(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setattr(
        cli, "make_ollama_client", lambda cfg: pytest.fail("ollama setup ran")
    )

    with caplog.at_level(logging.ERROR, logger="src.local_llm.cli"):
        rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 1
    assert any("BRAVE_API_KEY" in r.message for r in caplog.records)
