"""Tests for news clustering (#169)."""

from src.local_llm.briefing.cluster import (
    NewsCluster,
    cluster_news_hits,
    render_clusters_block,
)
from src.local_llm.briefing.prefetch import PrefetchedContext
from src.local_llm.search import SearchResult


def _ctx(*, macro=None, per_ticker=None) -> PrefetchedContext:
    return PrefetchedContext(
        macro=macro or [],
        per_ticker=per_ticker or {},
        geo_by_topic={},
        events_by_name={},
    )


def test_same_url_across_macro_and_ticker_collapses_into_one_cluster():
    hit = SearchResult("Fed holds rates", "https://e.com/fed", "FOMC decision")
    ctx = _ctx(macro=[hit], per_ticker={"PLTR": [hit], "NVDA": [hit]})

    clusters = cluster_news_hits(ctx)

    assert len(clusters) == 1
    # 同一 URL が macro/PLTR/NVDA から来ても 1 ストーリーに集約、source は統合
    assert clusters[0].primary.url == "https://e.com/fed"
    assert set(clusters[0].sources) == {"macro", "PLTR", "NVDA"}


def test_similar_titles_are_grouped_by_heuristic():
    a = SearchResult(
        "US weighs new chip export rule on China",
        "https://e.com/chip-a",
        "semiconductor export restriction china",
    )
    b = SearchResult(
        "New chip export rule on China weighed by US",
        "https://e.com/chip-b",
        "semiconductor export restriction china",
    )
    ctx = _ctx(macro=[a], per_ticker={"NVDA": [b]})

    clusters = cluster_news_hits(ctx)

    assert len(clusters) == 1
    urls = {r.url for r in clusters[0].results}
    assert urls == {"https://e.com/chip-a", "https://e.com/chip-b"}


def test_distinct_stories_stay_separate():
    a = SearchResult("Oil surges on Hormuz tension", "https://e.com/oil", "energy crude")
    b = SearchResult("PLTR wins defense contract", "https://e.com/pltr", "palantir gov deal")
    ctx = _ctx(macro=[a], per_ticker={"PLTR": [b]})

    clusters = cluster_news_hits(ctx)

    assert len(clusters) == 2


def test_embed_fn_is_used_when_provided():
    a = SearchResult("alpha story", "https://e.com/a", "x")
    b = SearchResult("totally different words", "https://e.com/b", "y")
    ctx = _ctx(macro=[a, b])

    # 埋め込みが同一ベクトルを返せば、トークンが全く違っても 1 クラスタに集約される
    def embed_fn(texts):
        return [[1.0, 0.0] for _ in texts]

    clusters = cluster_news_hits(ctx, embed_fn=embed_fn, threshold=0.9)
    assert len(clusters) == 1

    # 直交ベクトルを返せば別クラスタのまま
    def orthogonal(texts):
        return [[1.0, 0.0], [0.0, 1.0]]

    clusters2 = cluster_news_hits(ctx, embed_fn=orthogonal, threshold=0.5)
    assert len(clusters2) == 2


def test_geo_and_events_are_not_clustered():
    macro = SearchResult("M", "https://e.com/m", "d")
    ctx = PrefetchedContext(
        macro=[macro],
        per_ticker={},
        geo_by_topic={"米中": [SearchResult("G", "https://e.com/g", "dg")]},
        events_by_name={"FOMC": [SearchResult("E", "https://e.com/e", "de")]},
    )
    clusters = cluster_news_hits(ctx)
    all_urls = {r.url for c in clusters for r in c.results}
    assert all_urls == {"https://e.com/m"}


def test_empty_context_returns_no_clusters():
    assert cluster_news_hits(_ctx()) == []


def test_render_clusters_block_shows_story_sources_and_extra_links():
    a = SearchResult("Chip rule", "https://e.com/a", "export", content="本文ここ")
    b = SearchResult("Chip rule restated", "https://e.com/b", "export")
    cluster = NewsCluster()
    cluster.add(a, "macro")
    cluster.add(b, "NVDA")

    block = render_clusters_block([cluster])

    assert "### クラスタ済みニュース" in block
    assert "[Chip rule](https://e.com/a)" in block
    assert "関連: macro、NVDA" in block
    assert "本文抜粋: 本文ここ" in block
    assert "関連記事: [Chip rule restated](https://e.com/b)" in block


def test_render_clusters_block_flattens_newlines_in_description():
    hit = SearchResult("T", "https://e.com/t", "line1\nline2")
    cluster = NewsCluster()
    cluster.add(hit, "macro")

    block = render_clusters_block([cluster])
    assert "line1 line2" in block  # 改行はスペースへ平坦化


def test_render_clusters_block_truncates_long_description():
    hit = SearchResult("T", "https://e.com/t", "x" * 300)
    cluster = NewsCluster()
    cluster.add(hit, "macro")

    block = render_clusters_block([cluster])
    assert "x" * 200 in block  # 200 文字までは残る
    assert "x" * 210 not in block  # 上限超過は切り詰め
    assert "..." in block


def test_render_clusters_block_truncates_long_content():
    hit = SearchResult("T", "https://e.com/t", "d", content="y" * 600)
    cluster = NewsCluster()
    cluster.add(hit, "macro")

    block = render_clusters_block([cluster])

    assert "y" * 500 in block
    assert "y" * 510 not in block
    assert "..." in block


def test_cosine_rejects_mismatched_vector_lengths():
    import pytest

    a = SearchResult("a", "https://e.com/a", "x")
    b = SearchResult("b", "https://e.com/b", "y")
    ctx = _ctx(macro=[a, b])

    def bad_embed(texts):
        return [[1.0, 0.0], [1.0]]  # 次元不一致

    with pytest.raises(ValueError, match="equal-length"):
        cluster_news_hits(ctx, embed_fn=bad_embed, threshold=0.5)


def test_render_clusters_block_empty():
    assert "検索ヒットなし" in render_clusters_block([])
