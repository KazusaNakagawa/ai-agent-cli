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
    build_local_briefing_prompt,
    compose_briefing_md,
    generate_local_briefing,
    load_local_briefing_system_prompt,
    prefetch_briefing_context,
    render_web_context_block,
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
        conflicts=[Conflict(name="米中技術覇権争い", affected_sectors=["半導体"])],
    )
    pltr_hit = SearchResult("PLTR Q2", "https://e.com/pltr", "earnings beat")
    macro_hit = SearchResult("Markets", "https://e.com/mkt", "rally")
    geo_hit = SearchResult("China chips", "https://e.com/geo", "export rules")
    search = _StubSearch(
        responses={
            "stock market news 2026-06-09": [macro_hit],
            "PLTR stock news today": [pltr_hit],
            "MSFT stock news today": [],
            "GOOGL stock news today": [],
            "米中技術覇権争い today": [geo_hit],
        }
    )

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    # Every ticker was searched, even if 0 hits
    queried = [c["query"] for c in search.calls]
    assert "stock market news 2026-06-09" in queried
    assert "PLTR stock news today" in queried
    assert "MSFT stock news today" in queried
    assert "GOOGL stock news today" in queried
    assert "米中技術覇権争い today" in queried

    assert ctx.macro == [macro_hit]
    assert ctx.per_ticker["PLTR"] == [pltr_hit]
    assert ctx.per_ticker["MSFT"] == []
    assert ctx.per_ticker["GOOGL"] == []
    assert ctx.geo_topic == "米中技術覇権争い"
    assert ctx.geo_results == [geo_hit]


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
    assert "PLTR stock news today" in search.calls
    assert ctx.per_ticker["PLTR"] == []
    assert any("PLTR stock news today" in r.message for r in caplog.records)


def test_prefetch_skips_geo_when_no_conflicts_configured():
    cfg = _minimal_cfg(tickers=["PLTR"], conflicts=[])
    search = _StubSearch()

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    assert ctx.geo_topic is None
    assert ctx.geo_results == []
    queried = [c["query"] for c in search.calls]
    assert not any("today" in q and q != "stock market news 2026-06-09" and "stock news" not in q for q in queried)


def test_render_web_context_block_contains_all_sections():
    ctx = PrefetchedContext(
        macro=[SearchResult("M", "https://e.com/m", "d")],
        per_ticker={
            "PLTR": [SearchResult("P", "https://e.com/p", "dp")],
            "MSFT": [],
        },
        geo_topic="米中",
        geo_results=[SearchResult("G", "https://e.com/g", "dg")],
    )

    block = render_web_context_block(ctx)

    assert "マクロ・市場全体" in block
    assert "https://e.com/m" in block
    assert "**PLTR**" in block and "https://e.com/p" in block
    assert "**MSFT**" in block and "(検索ヒットなし)" in block
    assert "地政学トピック: 米中" in block
    assert "https://e.com/g" in block


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def test_build_local_briefing_prompt_injects_web_context():
    cfg = _minimal_cfg()
    out = build_local_briefing_prompt(
        cfg,
        stocks="PLTR +2.1%\nNVDA +0.5%",
        today="2026-06-09",
        web_context="### マクロ\n- foo",
    )

    assert "PLTR" in out
    assert "NVDA" in out
    assert "PLTR +2.1%" in out
    assert "2026-06-09" in out
    # The injected web_context block is present and labelled as the only source
    assert "### マクロ" in out
    assert "## 検索結果" in out
    # watch_sectors is intentionally not rendered (Claude-only scope).
    assert "AI & Cloud" not in out


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
        geo_topic=None,
        geo_results=[],
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
        geo_topic="x",
        geo_results=[SearchResult("g", "https://e.com/geo", "")],
    )
    body = "[m](https://e.com/macro) [p](https://e.com/pltr) [g](https://e.com/geo)"
    v = validate_urls(body, ctx)
    assert v.fabricated == 0
    assert v.verified == 3


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
                geo_topic=None,
                geo_results=[],
            )

        monkeypatch.setattr(cli, "prefetch_briefing_context", _fake_prefetch)
        monkeypatch.setattr(
            cli, "render_web_context_block", lambda ctx: "WEB_CTX"
        )
        monkeypatch.setattr(
            cli,
            "build_local_briefing_prompt",
            lambda cfg, stocks, today, web_context: (
                f"PROMPT(today={today}, ctx={web_context})"
            ),
        )
        monkeypatch.setattr(
            cli, "load_local_briefing_system_prompt", lambda: "SYS"
        )

        def _fake_generate(prompt, *, ollama_client, model, system_prompt):
            self.generate_calls.append(
                {"prompt": prompt, "system_prompt": system_prompt}
            )
            return briefing_text

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
    assert "### 今日" in content
    # Pre-fetch ran with the search client + tickers from briefing.json
    assert len(fake.prefetch_calls) == 1
    assert fake.prefetch_calls[0]["tickers"] == ["PLTR", "NVDA"]
    assert len(fake.search_clients) == 1
    # The injected web context reached the prompt
    assert "ctx=WEB_CTX" in fake.generate_calls[0]["prompt"]
    assert fake.generate_calls[0]["system_prompt"] == "SYS"
    # URL 検証行が caveat に入っている (今回は本文に URL なし → 0/0)
    assert "URL 検証" in content
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
