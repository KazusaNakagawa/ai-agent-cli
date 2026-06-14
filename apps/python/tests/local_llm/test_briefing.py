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
    OVERFETCH_EXTRA,
    STALE_ARTICLE_DAYS,
    PER_GEO_RESULTS,
    PER_MACRO_RESULTS,
    PER_TICKER_RESULTS,
    PrefetchedContext,
    UrlValidation,
    _extract_url_date,
    _is_index_page,
    _url_has_no_spaces,
    has_simplified_chinese_text,
    build_section_geo_events_prompt,
    build_section_insight_prompt,
    build_section_sector_prompt,
    build_section_topnews_prompt,
    collect_references,
    compose_briefing_md,
    ensure_geo_topics_covered,
    generate_local_briefing,
    load_local_briefing_system_prompt,
    prefetch_briefing_context,
    render_geo_events_block,
    render_macro_block,
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

    def search(self, query, count=5, freshness=None):
        self.calls.append({"query": query, "count": count, "freshness": freshness})
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

        def search(self, query, count=5, freshness=None):
            self.calls.append(query)
            if "PLTR" in query:
                raise BraveSearchError("HTTP 429: rate limited")
            return []

    search = _FailingSearch()
    with caplog.at_level(logging.WARNING, logger="src.local_llm.briefing.prefetch"):
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


def test_prefetch_requests_freshness_and_overfetch_on_every_query():
    cfg = _minimal_cfg(
        tickers=["PLTR"],
        conflicts=[Conflict(name="米中", affected_sectors=["半導体"])],
    )
    search = _StubSearch()

    prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    assert search.calls, "search が呼ばれていない"
    # 直近 1 週間に絞り、索引ページフィルタの間引き分を over-fetch する (#153)
    for call in search.calls:
        assert call["freshness"] == "pw"
    by_query = {c["query"]: c for c in search.calls}
    assert by_query["stock market news 2026-06-09"]["count"] == (
        PER_MACRO_RESULTS + OVERFETCH_EXTRA
    )
    assert by_query["PLTR stock news 2026-06-09"]["count"] == (
        PER_TICKER_RESULTS + OVERFETCH_EXTRA
    )
    assert by_query["米中 today"]["count"] == PER_GEO_RESULTS + OVERFETCH_EXTRA


def test_prefetch_filters_index_pages_and_trims_to_count():
    cfg = _minimal_cfg(tickers=["PLTR"], conflicts=[])
    news = [
        SearchResult(f"News {i}", f"https://news.example.com/{i}", "d")
        for i in range(PER_TICKER_RESULTS + 1)
    ]
    index_pages = [
        SearchResult("Quote", "https://finance.yahoo.com/quote/PLTR/", "d"),
        SearchResult("RH", "https://robinhood.com/us/en/stocks/PLTR/", "d"),
        SearchResult("GF", "https://www.google.com/finance/beta/quote/PLTR:NASDAQ", "d"),
        SearchResult("Inv", "https://www.investing.com/equities/palantir", "d"),
        SearchResult("SA", "https://stockanalysis.com/stocks/pltr/", "d"),
        SearchResult("SeekA", "https://seekingalpha.com/symbol/PLTR", "d"),
        SearchResult("Book", "https://www.amazon.co.jp/dp/4582859879", "d"),
        SearchResult("CNBCq", "https://www.cnbc.com/quotes/PLTR", "d"),
    ]
    search = _StubSearch(
        responses={"PLTR stock news 2026-06-09": index_pages[:2] + news}
    )

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    # 索引ページは除外され、残りが PER_TICKER_RESULTS 件に切り詰められる
    assert ctx.per_ticker["PLTR"] == news[:PER_TICKER_RESULTS]
    for r in index_pages:
        assert _is_index_page(r.url), r.url
    # 商品名スラッグ付きの Amazon 商品ページ (local_2026-06-11 で実際に汚染した形)
    assert _is_index_page("https://www.amazon.co.jp/%E5%8F%B0%E6%B9%BE%E6%9C%89%E4%BA%8B-987/dp/4582859879")
    assert not _is_index_page("https://news.example.com/article-1")
    # Amazon の記事系ページ (商品詳細以外) は除外しない
    assert not _is_index_page("https://www.aboutamazon.com/news/company-news/q1-results")
    assert not _is_index_page("https://www.amazon.com/press-release/some-news")
    # CNBC の記事 (/YYYY/MM/DD/...) は残す — クオートページ (/quotes/) のみ除外
    assert not _is_index_page(
        "https://www.cnbc.com/2026/06/02/stock-market-today-live-updates.html"
    )


def test_is_index_page_filters_forecast_and_rating_sites():
    # 株価予想・アナリストレーティングの集約ページは当日のニュースではなく
    # 常設の目標株価/予想ページ。投資判断価値が低く注入コンテキストを汚すため
    # 除外する (#158)。パスを `/stocks/` 等に絞り、各サイトの記事系ページは残す。
    forecast_pages = [
        "https://www.marketbeat.com/stocks/NASDAQ/PLTR/price-target/",
        "https://www.marketbeat.com/stocks/NASDAQ/PLTR/forecast/",
        "https://simplywall.st/stocks/us/tech/nyse-pltr/palantir-technologies",
        "https://www.tipranks.com/stocks/pltr/forecast",
        "https://www.wallstreetzen.com/stocks/us/nasdaq/pltr/stock-forecast",
        "https://www.cnn.com/markets/stocks/PLTR",
        # 13F 保有変動の自動量産スパム & レーティング/煽り系 (実機検証で表を汚した)
        "https://www.americanbankingnews.com/2026/06/12/isrg-stake-lifted.html",
        "https://www.dailypolitical.com/2026/06/10/raises-stake-in-dexcom-dxcm.html",
        "https://www.themarketsdaily.com/2026/06/10/increases-stock-position-dxcm.html",
        "https://weissratings.com/en/instant-news-alerts/dexcom-inc-dxcm-up-5-9",
        "https://www.timothysykes.com/news/leverage-shares-2x-long-cbrs-2026_06_10/",
        "https://stockstotrade.com/news/cerebras-systems-inc-cbrs-news-2026_06_08-3/",
        # クオート/ライブ株価の索引ページ & バリュエーション予想サイト (#176)
        "https://www.indmoney.com/us-stocks/alphabet-inc-class-a-shares-share-price-googl",
        "https://www.trefis.com/stock/googl/articles/602686/does-google-stock-have-more-upside/2026-06-12",
        # 13F スパム・/instant-alerts/ は /stocks/ 限定フィルタを回避していたため全ドメイン除外 (#180)
        "https://www.marketbeat.com/",
        "https://www.marketbeat.com/instant-alerts/filing-macquarie-group-ltd-raises-stock-holdings-in-palantir/",
        "https://www.marketbeat.com/originals/some-news-article/",
    ]
    for url in forecast_pages:
        assert _is_index_page(url), url
    assert not _is_index_page("https://www.tipranks.com/news/some-article")
    # 一次情報メディアの記事は当然残す
    assert not _is_index_page("https://www.reuters.com/markets/us/article-1")
    assert not _is_index_page("https://www.cnbc.com/2026/06/13/some-news.html")
    # fool.com / 247wallst は良質記事も混じるため除外しない (意図的に残す)
    assert not _is_index_page(
        "https://www.fool.com/investing/2026/06/08/prediction-palantir-stock-5-years/"
    )
    assert not _is_index_page(
        "https://247wallst.com/investing/2026/06/10/microsoft-stock-prediction/"
    )
    # indmoney / trefis はパス限定 — クオート/予想ページ以外の記事は残す
    assert not _is_index_page("https://www.indmoney.com/blog/how-to-invest-in-us-stocks")
    assert not _is_index_page("https://www.trefis.com/insights/some-market-commentary")


def test_prefetch_drops_urls_with_spaces():
    # スペースを含む URL は不正形式。Markdown リンク崩壊 → <URL未検証> の原因 (#181)。
    cfg = _minimal_cfg(tickers=["PLTR"])
    bad = SearchResult("Bad", "https://example.com/Some Article Title", "d")
    good = SearchResult("Good", "https://example.com/valid-article-123", "d")
    search = _StubSearch(responses={"PLTR stock news 2026-06-09": [bad, good]})

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    assert ctx.per_ticker["PLTR"] == [good]
    assert not _url_has_no_spaces(bad.url)
    assert _url_has_no_spaces(good.url)


def test_extract_url_date_common_patterns():
    from datetime import date
    # CNBC style: /YYYY/MM/DD/
    assert _extract_url_date("https://www.cnbc.com/2026/06/01/stock-market-today.html") == date(2026, 6, 1)
    # Bloomberg style: /YYYY-MM-DD/
    assert _extract_url_date("https://www.bloomberg.com/news/articles/2026-06-14/story") == date(2026, 6, 14)
    # Investopedia style: -MMDDYYYY-
    assert _extract_url_date("https://www.investopedia.com/news-06092026-11993707") == date(2026, 6, 9)
    # No date in URL
    assert _extract_url_date("https://www.reuters.com/world/ukraine-russia-war/") is None


def test_prefetch_drops_stale_articles():
    from datetime import date
    cfg = _minimal_cfg(tickers=["PLTR"])
    stale = SearchResult("Old", "https://www.cnbc.com/2026/06/01/old-news.html", "d")
    fresh = SearchResult("New", "https://www.cnbc.com/2026/06/13/new-news.html", "d")
    no_date = SearchResult("NoDt", "https://www.reuters.com/world/some-story/", "d")
    search = _StubSearch(responses={"PLTR stock news 2026-06-14": [stale, fresh, no_date]})

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-14")

    pltr_urls = [r.url for r in ctx.per_ticker["PLTR"]]
    assert stale.url not in pltr_urls, "stale article (12 days old) should be filtered"
    assert fresh.url in pltr_urls, "fresh article (1 day old) should pass"
    assert no_date.url in pltr_urls, "no-date URL should pass (can't determine age)"


def test_has_simplified_chinese_text_detects_simplified_chinese():
    # 002 実行で実際に出力された簡体字行 (#179)
    assert has_simplified_chinese_text("什么变了：标普500指数创下历史新高")
    assert has_simplified_chinese_text("对持有股票的影响：PLTR はリスク")
    assert has_simplified_chinese_text("为什么发生：AIチップ輸出規制")
    # 簡体字固有文字の単独チェック
    for ch in "么这们该为标对创历发说变实响":
        assert has_simplified_chinese_text(ch), f"Expected to detect Chinese char: {ch}"


def test_has_simplified_chinese_text_passes_japanese():
    # 日本語テキストは誤検出しない
    assert not has_simplified_chinese_text("なぜ起きたか: S&P 500 が過去最高値を更新した")
    assert not has_simplified_chinese_text("何が変わったか: テクノロジー株全体が上昇した")
    assert not has_simplified_chinese_text("保有銘柄への影響: MSFT・GOOGL に追い風")
    assert not has_simplified_chinese_text("半導体輸出規制の強化により台湾リスクが高まった")
    assert not has_simplified_chinese_text("Palantir Technologies の時価総額が記録を更新")
    # 漢字のみの行でも日本語で使う文字なら検出しない
    assert not has_simplified_chinese_text("米中技術覇権争い・台湾リスク")


def test_prefetch_uses_english_geo_query_when_query_en_set():
    cfg = _minimal_cfg(
        tickers=["PLTR"],
        conflicts=[
            Conflict(
                name="ロシア・ウクライナ戦争",
                affected_sectors=["エネルギー"],
                query_en="Russia Ukraine war",
            ),
            Conflict(name="米中", affected_sectors=["半導体"]),
        ],
    )
    geo_hit = SearchResult("RU war", "https://e.com/ru", "d")
    search = _StubSearch(responses={"Russia Ukraine war latest news": [geo_hit]})

    ctx = prefetch_briefing_context(cfg, search_client=search, today="2026-06-09")

    queried = [c["query"] for c in search.calls]
    # query_en があれば英語ニュースクエリ、なければ従来の日本語クエリ
    assert "Russia Ukraine war latest news" in queried
    assert "ロシア・ウクライナ戦争 today" not in queried
    assert "米中 today" in queried
    # 結果のキーは表示用に日本語トピック名のまま
    assert ctx.geo_by_topic["ロシア・ウクライナ戦争"] == [geo_hit]


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
    cfg = _minimal_cfg(tickers=["PLTR", "NVDA"])
    ctx = _full_ctx()
    out = build_section_topnews_prompt(cfg, ctx=ctx, today="2026-06-09")
    assert "今日のトップニュース" in out
    assert "2026-06-09" in out
    assert "## 検索結果" in out
    assert "https://e.com/m" in out
    # 出典は macro ブロックのみ — 銘柄別 URL・地政学ブロックはこの段では渡さない
    assert "https://e.com/p" not in out
    assert "地政学" not in out


def test_topnews_prompt_drives_causal_holding_analysis():
    # 各トップニュースに「なぜ / 何が変わった / 保有銘柄への影響」の因果 3 行を
    # 要求し、影響判定用に保有銘柄リストを渡す (#159)。
    cfg = _minimal_cfg(tickers=["PLTR", "NVDA"])
    ctx = _full_ctx()
    out = build_section_topnews_prompt(cfg, ctx=ctx, today="2026-06-09")
    assert "なぜ" in out
    assert "何が変わった" in out
    assert "保有銘柄" in out
    assert "PLTR" in out
    assert "NVDA" in out




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


def test_geo_events_prompt_drops_topics_without_investable_channel():
    # 投資チャネル (原油/金/半導体/防衛/AI/金融制裁/サプライチェーン) で波及を
    # 説明できないトピックは要約せず落とす指示を出す (#160)。波及判定行は維持。
    cfg = _minimal_cfg(tickers=["PLTR", "NVDA"])
    ctx = _full_ctx()
    out = build_section_geo_events_prompt(cfg, ctx=ctx, today="2026-06-09")
    assert "投資チャネル" in out
    assert "除外" in out
    # 関税・貿易戦争は供給網チャネル直結として除外しない指示 (#173 後の検証)
    assert "関税" in out
    # 既存の保有銘柄波及判定の指示は残っている
    assert "保有銘柄への波及" in out


def test_ensure_geo_topics_covered_appends_omitted_topics():
    # モデルが投資影響あるトピック (中東=原油) を黙って省略しても、Python 側で
    # `### {topic}` 見出しと pre-fetch リンクを補完する (#175)。
    ctx = PrefetchedContext(
        macro=[],
        per_ticker={},
        geo_by_topic={
            "中東紛争": [SearchResult("Iran-Israel", "https://e.com/mid", "d")],
            "米中": [SearchResult("Chips", "https://e.com/cn", "d")],
        },
        events_by_name={},
    )
    # モデル出力は米中だけ。中東は省略されている。
    body = "## 地政学トピック\n\n### 米中\n要約 [出典](https://e.com/cn)"
    out = ensure_geo_topics_covered(body, ctx)
    # 省略された中東が見出し付きで補完され、リンクも残る
    assert "### 中東紛争" in out
    assert "https://e.com/mid" in out
    # 既に出ている米中は重複追記しない
    assert out.count("### 米中") == 1


def test_ensure_geo_topics_covered_noop_when_all_present():
    ctx = PrefetchedContext(
        macro=[],
        per_ticker={},
        geo_by_topic={"米中": [SearchResult("Chips", "https://e.com/cn", "d")]},
        events_by_name={},
    )
    body = "### 米中\n要約"
    assert ensure_geo_topics_covered(body, ctx) == body


def test_ensure_geo_topics_covered_marks_topic_without_hits():
    # 検索ヒット 0 件のトピックも見出し付きで残し、「検索でも確認できず」を出す。
    ctx = PrefetchedContext(
        macro=[],
        per_ticker={},
        geo_by_topic={"インド・パキスタン": []},
        events_by_name={},
    )
    out = ensure_geo_topics_covered("## 地政学トピック", ctx)
    assert "### インド・パキスタン" in out
    assert "検索でも確認できず" in out


def test_ensure_geo_topics_covered_inserts_before_events_section():
    """省略トピックは ## 監視イベント の前に挿入すること (006 regression: 後ろに出てしまった)。"""
    ctx = PrefetchedContext(
        macro=[],
        per_ticker={},
        geo_by_topic={
            "米中": [SearchResult("Chips", "https://e.com/cn", "d")],
            "インド・パキスタン": [SearchResult("India", "https://e.com/in", "d")],
        },
        events_by_name={},
    )
    body = (
        "## 地政学トピック\n\n### 米中\n要約\n\n"
        "## 監視イベント\n- SpaceX IPO"
    )
    out = ensure_geo_topics_covered(body, ctx)
    # インド・パキスタンが ## 監視イベント より前にあること
    assert "### インド・パキスタン" in out
    events_pos = out.index("## 監視イベント")
    india_pos = out.index("### インド・パキスタン")
    assert india_pos < events_pos, "missing topic must be inserted BEFORE ## 監視イベント"


def test_ensure_geo_topics_covered_noop_when_no_geo_topics():
    # geo_by_topic が空なら何も補完しない (early return)。
    ctx = PrefetchedContext(
        macro=[], per_ticker={}, geo_by_topic={}, events_by_name={}
    )
    body = "## 地政学トピック\n\n### 米中\n要約"
    assert ensure_geo_topics_covered(body, ctx) == body


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


def test_compose_briefing_md_includes_article_summary_line():
    md = compose_briefing_md(
        body="b",
        model="qwen2.5:14b",
        generated_at=datetime(2026, 6, 9, 9, 15, 0),
        article_summary="10/12 件取得",
    )
    assert "記事本文: 10/12 件取得" in md










def test_build_section_insight_prompt_carries_prior_text_and_themes():
    cfg = _minimal_cfg()
    out = build_section_insight_prompt(
        cfg, prior_text="### マクロ\n本文", today="2026-06-09"
    )
    assert "自分への示唆" in out
    assert "AI" in out  # themes
    assert "本文" in out


def test_insight_prompt_uses_pm_buy_watch_event_blocks():
    # PM 視点の構造化: 買い増し候補 → 注意銘柄 → 監視イベント を
    # この順序で要求する (#161)。
    cfg = _minimal_cfg()
    out = build_section_insight_prompt(
        cfg, prior_text="### マクロ\n本文", today="2026-06-09"
    )
    # 3 ブロックが揃い、買い増し候補 → 注意銘柄 → 監視イベント の順で並ぶ
    # (.index は未検出で ValueError を投げるので存在確認も兼ねる)
    i_buy = out.index("買い増し候補")
    i_watch = out.index("注意銘柄")
    i_event = out.index("監視イベント")
    assert i_buy < i_watch < i_event
    # 学習知識可・URL 不可 (捏造防止): 指示が明記され、テンプレ自体に URL を含まない
    assert "URL は書かないこと" in out
    assert "http" not in out


def test_build_section_sector_prompt_maps_news_to_holdings():
    # トップニュース本文 (prior_text) から波及セクターを導出し、保有銘柄へ接続する (#162)。
    cfg = _minimal_cfg(tickers=["PLTR", "NVDA"])
    out = build_section_sector_prompt(
        cfg, prior_text="## 今日のトップニュース\nNVDA 決算", today="2026-06-09"
    )
    assert "セクター影響" in out
    assert "該当する保有" in out  # 保有銘柄への接続を必須化
    assert "PLTR" in out
    assert "NVDA" in out
    # prior_text (トップニュース本文) が注入される
    assert "NVDA 決算" in out
    # 新規 URL は書かない制約 (出典はトップニュース側に既出)
    assert "URL" in out


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

    def chat(self, *, model, messages, options=None):
        self.calls.append(
            {"model": model, "messages": list(messages), "options": options}
        )
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


def test_generate_local_briefing_passes_options_to_chat():
    olm = _ScriptedOllama(reply={"message": {"content": "body"}})
    generate_local_briefing(
        "PROMPT",
        ollama_client=olm,
        model="m",
        options={"num_ctx": 16384, "temperature": 0.2},
    )
    assert olm.calls[0]["options"] == {"num_ctx": 16384, "temperature": 0.2}


def test_generate_local_briefing_defaults_to_no_options(caplog):
    olm = _ScriptedOllama(reply={"message": {"content": "body"}})
    with caplog.at_level(logging.INFO, logger="src.local_llm.briefing.generate"):
        generate_local_briefing("PROMPT", ollama_client=olm, model="m")
    # options 未指定の既存呼び出しは chat() に None を渡す (後方互換)
    assert olm.calls[0]["options"] is None
    # num_ctx 不明時は警告ではなく info で「Ollama 既定」と記録する
    assert not any(r.levelname == "WARNING" for r in caplog.records)
    assert any("(Ollama 既定)" in r.getMessage() for r in caplog.records)


def test_generate_local_briefing_warns_when_prompt_exceeds_num_ctx(caplog):
    olm = _ScriptedOllama(reply={"message": {"content": "body"}})
    with caplog.at_level(logging.WARNING, logger="src.local_llm.briefing.generate"):
        generate_local_briefing(
            "x" * 100,
            ollama_client=olm,
            model="m",
            options={"num_ctx": 10},
        )
    assert any(
        r.levelname == "WARNING" and "num_ctx=10" in r.getMessage()
        for r in caplog.records
    )


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


def test_validate_urls_url_with_close_paren_does_not_leave_garbage():
    """Brave Search returns URLs containing ) — validate_urls must not leave trailing garbage."""
    ctx = _ctx_with_urls("https://e.com/real")
    # URL contains ) in the middle (as seen with PLTR Brave hit in 003)
    body = "[title](https://fabricated.com/path)+Opinions+on+Recent) あと [real](https://e.com/real)"
    v = validate_urls(body, ctx)
    assert ")+Opinions" not in v.body
    assert v.fabricated == 1
    assert "https://e.com/real" in v.body


def test_collect_references_matches_url_inside_markdown_link():
    """collect_references must match pre-fetch URLs even when body wraps them in [title](url)."""
    ctx = _ctx_with_urls(
        "https://www.reuters.com/world/ukraine-russia-war/",
        "https://e.com/other",
    )
    body = (
        "[Reuters](https://www.reuters.com/world/ukraine-russia-war/) "
        "と [Other](https://e.com/other)"
    )
    md = collect_references(ctx, body)
    assert "reuters.com" in md
    assert "e.com/other" in md
    assert "pre-fetch 外" not in md


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
        self.table_calls: list[dict] = []
        self.topnews_cfg = None
        self.sector_prior = None

        monkeypatch.setenv("BRAVE_API_KEY", "test-brave-key")
        monkeypatch.setattr(cli, "BRIEFING_OUTPUT_DIR", self.output_dir)
        monkeypatch.setattr(
            cli,
            "fetch_stock_move_map",
            lambda tickers: {t: "↑1.0%  ($100.00)" for t in tickers},
        )
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

        def _fake_topnews(cfg, *, ctx, today):
            # CLI が briefing_cfg (tickers 込み) をそのまま渡しているか検証用に捕捉
            self.topnews_cfg = cfg
            return f"PROMPT_TOP(today={today})"

        monkeypatch.setattr(cli, "build_section_topnews_prompt", _fake_topnews)

        def _fake_sector(cfg, *, prior_text, today):
            # セクター段がトップニュース本文を prior_text として受けているか捕捉
            self.sector_prior = prior_text
            return f"PROMPT_SECTOR(today={today})"

        monkeypatch.setattr(cli, "build_section_sector_prompt", _fake_sector)
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

        def _fake_table(tickers, *, ctx, moves, ollama_client, model, options=None, today):
            self.table_calls.append(
                {
                    "tickers": list(tickers),
                    "moves": dict(moves),
                    "options": options,
                    "today": today,
                }
            )
            return (
                "## 保有銘柄テーブル\n\n"
                "| 銘柄 | 値動き | 今日のトピック (1 行) | 出典 |\n"
                "|---|---|---|---|\n"
                "| PLTR | ↑1.0%  ($100.00) | (確認できず) | - |"
            )

        monkeypatch.setattr(cli, "generate_portfolio_table", _fake_table)

        def _fake_generate(prompt, *, ollama_client, model, system_prompt, options=None):
            self.generate_calls.append(
                {"prompt": prompt, "system_prompt": system_prompt, "options": options}
            )
            # 自由生成は 3 段 (top / geo / insight)。保有銘柄テーブルは
            # generate_portfolio_table の構造化経路 (#152) で別 stub。テストごとに
            # 変えたい本文 (URL 捏造を仕込む等) は 1 段目 (topnews) に集約する。
            if "PROMPT_TOP" in prompt:
                return briefing_text
            if "PROMPT_SECTOR" in prompt:
                return "## セクター影響"
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
    # CLI が briefing_cfg (tickers 込み) を topnews builder に渡している (#159)
    assert fake.topnews_cfg is not None
    assert fake.topnews_cfg.portfolio.tickers == ["PLTR", "NVDA"]
    assert len(fake.search_clients) == 1
    # 自由生成 4 段 (top → sector → geo → insight) + 構造化テーブル 1 回 (#162)
    assert len(fake.generate_calls) == 4
    prompts = [c["prompt"] for c in fake.generate_calls]
    assert "PROMPT_TOP" in prompts[0]
    assert "PROMPT_SECTOR" in prompts[1]
    assert "PROMPT_GEO" in prompts[2]
    assert "PROMPT_INS" in prompts[3]
    # セクター段はトップニュース本文を prior_text として受ける (#162)
    assert fake.sector_prior is not None
    assert "### 今日" in fake.sector_prior
    # insight 段には先行段の本文 (セクター・テーブル含む) が prior_text として渡る
    assert "保有銘柄テーブル" in prompts[3]
    assert "セクター影響" in prompts[3]
    # テーブルは構造化経路 (#152) に全銘柄 + 実値動き + 生成オプションが渡る
    assert len(fake.table_calls) == 1
    assert fake.table_calls[0]["tickers"] == ["PLTR", "NVDA"]
    assert fake.table_calls[0]["moves"]["PLTR"] == "↑1.0%  ($100.00)"
    assert fake.table_calls[0]["options"]["num_ctx"] == 16384
    # 全段に同じ system prompt が乗る
    assert all(c["system_prompt"] == "SYS" for c in fake.generate_calls)
    # 全段に cfg 由来の生成オプションが乗る (#150 — Ollama 既定 num_ctx 回避)
    for c in fake.generate_calls:
        assert c["options"] is not None
        assert c["options"]["num_ctx"] == 16384
        assert c["options"]["temperature"] == 0.2
    # 参考記事セクションが Python 側で追加されている
    assert "## 参考記事" in content
    # 構造化経路が組んだテーブルがそのまま本文に入る
    assert "## 保有銘柄テーブル" in content
    assert "|---|---|---|---|" in content
    # 本文は 世界(トップニュース) → セクター → 地政学 → 銘柄(テーブル) → 示唆 の順 (#162)
    markers = ["### 今日", "セクター影響", "地政学トピック", "保有銘柄テーブル", "自分への示唆"]
    # 各見出しは 1 回だけ出る (重複だと .index ベースの順序判定が偽陽性になりうる)
    for m in markers:
        assert content.count(m) == 1, m
    order = [content.index(m) for m in markers]
    assert order == sorted(order)
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


def test_cmd_briefing_regens_on_chinese_output(monkeypatch, tmp_path, caplog):
    """中国語テキストが出たら再生成して日本語に戻す (#179)。"""
    fake = _FakeRunCLI(monkeypatch, tmp_path)
    topnews_calls = {"n": 0}

    def _gen_chinese_then_ja(prompt, *, ollama_client, model, system_prompt, options=None):
        if "PROMPT_TOP" in prompt:
            topnews_calls["n"] += 1
            if topnews_calls["n"] == 1:
                return "## 今日のトップニュース\n- なぜ起きたか: 什么变了：标普500\n"
            return "## 今日のトップニュース\n- なぜ起きたか: S&P 500 が過去最高値を更新した\n"
        if "PROMPT_SECTOR" in prompt:
            return "## セクター影響"
        if "PROMPT_GEO" in prompt:
            return "## 地政学トピック"
        if "PROMPT_INS" in prompt:
            return "## 自分への示唆"
        return ""

    monkeypatch.setattr(cli, "generate_local_briefing", _gen_chinese_then_ja)

    with caplog.at_level(logging.WARNING, logger="src.local_llm.cli"):
        rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    assert topnews_calls["n"] == 2  # re-generated exactly once
    content = list(fake.output_dir.glob("local_*.md"))[0].read_text()
    assert "什么变了" not in content
    assert "S&P 500 が過去最高値" in content
    assert any("中国語" in r.message for r in caplog.records)


def test_cmd_briefing_without_brave_api_key_fails_fast(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setattr(
        cli, "make_ollama_client", lambda cfg: pytest.fail("ollama setup ran")
    )

    with caplog.at_level(logging.ERROR, logger="src.local_llm.cli"):
        rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 1
    assert any("BRAVE_API_KEY" in r.message for r in caplog.records)
