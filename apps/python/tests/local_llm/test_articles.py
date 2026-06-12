import logging

from src.local_llm.articles import (
    MAX_ARTICLE_CHARS,
    _fetch_article_text,
    count_article_fetches,
    enrich_with_article_text,
)
from src.local_llm.briefing import PrefetchedContext, _format_results
from src.local_llm.search import SearchResult

_ARTICLE_HTML = """<html><head><title>PLTR News</title></head><body>
<nav>Home | Markets | Tech</nav>
<article>
<h1>Palantir wins major defense contract</h1>
<p>Palantir Technologies announced on Friday that it has secured a $480 million
contract with the US Army to expand its Maven Smart System. The deal extends
through 2029 and covers AI-enabled targeting workflows.</p>
<p>Shares rose 3.2% in pre-market trading following the announcement. Analysts
at Morgan Stanley maintained their overweight rating with a price target of $145.</p>
</article>
<footer>Copyright 2026</footer>
</body></html>"""


class _FakeResp:
    def __init__(self, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeHTTP:
    """get(url, headers=...) を持つテスト用クライアント。URL ごとに応答を返す。"""

    def __init__(self, responses: dict[str, _FakeResp] | None = None):
        self.responses = responses or {}
        self.calls: list[str] = []

    def get(self, url, headers=None):
        self.calls.append(url)
        if url not in self.responses:
            raise ConnectionError("no route")
        return self.responses[url]


# ---------------------------------------------------------------------------
# _fetch_article_text
# ---------------------------------------------------------------------------


def test_fetch_article_text_extracts_main_text_without_nav_footer():
    http = _FakeHTTP({"https://e.com/a": _FakeResp(200, _ARTICLE_HTML)})

    text = _fetch_article_text("https://e.com/a", http_client=http)

    assert "$480 million" in text
    assert "Maven Smart System" in text
    # 本文以外 (nav / footer) は落ちる
    assert "Copyright" not in text
    assert "Home | Markets" not in text
    # 改行は畳まれて 1 行になる (markdown リスト内に注入するため)
    assert "\n" not in text


def test_fetch_article_text_truncates_to_max_chars():
    http = _FakeHTTP({"https://e.com/a": _FakeResp(200, _ARTICLE_HTML)})

    text = _fetch_article_text("https://e.com/a", http_client=http, max_chars=50)

    assert len(text) == 50 + len("...")
    assert text.endswith("...")


def test_fetch_article_text_returns_empty_on_connection_error(caplog):
    http = _FakeHTTP()  # 全 URL で ConnectionError

    with caplog.at_level(logging.WARNING, logger="src.local_llm.articles"):
        text = _fetch_article_text("https://e.com/down", http_client=http)

    assert text == ""
    assert any("fetch failed" in r.message for r in caplog.records)


def test_fetch_article_text_returns_empty_on_http_error(caplog):
    http = _FakeHTTP({"https://e.com/403": _FakeResp(403, "forbidden")})

    with caplog.at_level(logging.WARNING, logger="src.local_llm.articles"):
        text = _fetch_article_text("https://e.com/403", http_client=http)

    assert text == ""
    assert any("HTTP 403" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# enrich_with_article_text
# ---------------------------------------------------------------------------


def _ctx() -> PrefetchedContext:
    return PrefetchedContext(
        macro=[
            SearchResult("M1", "https://e.com/m1", "dm1"),
            SearchResult("M2", "https://e.com/m2", "dm2"),
            SearchResult("M3", "https://e.com/m3", "dm3"),
        ],
        per_ticker={
            "PLTR": [
                SearchResult("P1", "https://e.com/p1", "dp1"),
                SearchResult("P2", "https://e.com/p2", "dp2"),
            ],
            "MSFT": [],
        },
        geo_by_topic={"米中": [SearchResult("G1", "https://e.com/g1", "dg1")]},
        events_by_name={},
    )


def test_enrich_fills_content_only_for_top_hits():
    ok = _FakeResp(200, _ARTICLE_HTML)
    http = _FakeHTTP(
        {
            "https://e.com/m1": ok,
            "https://e.com/m2": ok,
            "https://e.com/p1": ok,
            "https://e.com/g1": ok,
        }
    )

    out = enrich_with_article_text(_ctx(), http_client=http, per_macro=2, per_group=1)

    # macro は上位 2 件、ticker/geo は上位 1 件だけ fetch される
    assert sorted(http.calls) == [
        "https://e.com/g1",
        "https://e.com/m1",
        "https://e.com/m2",
        "https://e.com/p1",
    ]
    assert "$480 million" in out.macro[0].content
    assert "$480 million" in out.macro[1].content
    assert out.macro[2].content == ""
    assert "$480 million" in out.per_ticker["PLTR"][0].content
    assert out.per_ticker["PLTR"][1].content == ""
    assert "$480 million" in out.geo_by_topic["米中"][0].content
    # 元の ctx は不変 (frozen dataclass の新インスタンスを返す)
    assert _ctx().macro[0].content == ""


def test_enrich_falls_back_to_snippet_on_fetch_failure():
    http = _FakeHTTP({"https://e.com/m1": _FakeResp(200, _ARTICLE_HTML)})
    # p1 / g1 / m2 は ConnectionError になる

    out = enrich_with_article_text(_ctx(), http_client=http, per_macro=2, per_group=1)

    assert "$480 million" in out.macro[0].content
    # 失敗したヒットはスニペットのまま (content 空) で残り、全体は止まらない
    assert out.macro[1].content == ""
    assert out.per_ticker["PLTR"][0].content == ""
    assert out.per_ticker["PLTR"][0].title == "P1"


def test_count_article_fetches_reports_attempted_and_fetched():
    http = _FakeHTTP({"https://e.com/m1": _FakeResp(200, _ARTICLE_HTML)})
    out = enrich_with_article_text(_ctx(), http_client=http, per_macro=2, per_group=1)

    attempted, fetched = count_article_fetches(out, per_macro=2, per_group=1)

    # m1, m2, p1, g1 の 4 件試行、成功は m1 のみ
    assert attempted == 4
    assert fetched == 1


# ---------------------------------------------------------------------------
# プロンプト注入 (_format_results との結合)
# ---------------------------------------------------------------------------


def test_format_results_includes_article_content_when_present():
    results = [
        SearchResult("T1", "https://e.com/1", "snippet only"),
        SearchResult("T2", "https://e.com/2", "with body", content="本文テキスト $480M"),
    ]

    block = _format_results(results)

    assert "本文抜粋: 本文テキスト $480M" in block
    # content が無いヒットには本文行が付かない
    lines = block.splitlines()
    assert lines[0].startswith("  - [T1]")
    assert "本文抜粋" not in lines[0]
