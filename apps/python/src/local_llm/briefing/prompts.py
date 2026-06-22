"""Per-section generation prompt construction and system-prompt loading.

Section split: generating all 9 sections in a single chat() scatters attention
and caused frequent URL fabrication in places like the holdings table. Splitting
into top news / sector / geopolitics+events / insight stages, and narrowing the
web_context passed to each stage to just that section's portion, stabilizes
citation following. The holdings table is separated into portfolio.py's
structured-output path (#152).
"""

from __future__ import annotations

from src.config import BriefingConfig
from src.generator.briefing import join_safe
from src.generator.prompt import render

from .cluster import (
    TOP_NEWS_CLUSTER_LIMIT,
    EmbedFn,
    cluster_news_hits,
    rank_clusters,
    render_clusters_block,
)
from .prefetch import PrefetchedContext
from .render import render_geo_events_block


def build_section_topnews_prompt(
    cfg: BriefingConfig, *, ctx: PrefetchedContext, today: str, embed_fn: EmbedFn | None = None
) -> str:
    """Top-news generation prompt.

    cfg is taken so the model always judges "each news item's impact on the
    holdings ($tickers)" as part of the 3-line causal block (#159).

    Sources are macro + per-ticker hits, clustered into deduplicated stories
    (#169) so the same event surfaced under several tickers/macro is presented
    once. Clusters are then ranked by investment importance and capped to the
    top ``TOP_NEWS_CLUSTER_LIMIT`` so the section leads with material catalysts
    (#170). ``embed_fn`` optionally supplies bge-m3 embeddings for clustering;
    omitted, a deterministic offline heuristic is used. Geopolitical/event hits
    are still routed to their own section, not here.
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    clusters = cluster_news_hits(ctx, embed_fn=embed_fn)
    clusters = rank_clusters(clusters, limit=TOP_NEWS_CLUSTER_LIMIT)
    return render(
        "local_section_topnews",
        today=today,
        tickers=tickers,
        web_context=render_clusters_block(clusters),
    )


def build_section_sector_prompt(
    cfg: BriefingConfig, *, prior_text: str, today: str
) -> str:
    """Prompt that extracts affected sectors from the top-news body and connects them to holdings (#162).

    The middle layer of the world → sector → ticker narrative. Sources already
    appear on the top-news side, so do not have it write new URLs (have it
    reference prior_text, as with insight).
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    return render(
        "local_section_sector",
        today=today,
        tickers=tickers,
        prior_text=prior_text,
    )


def build_section_geo_events_prompt(
    cfg: BriefingConfig, *, ctx: PrefetchedContext, today: str
) -> str:
    """Geopolitics+events generation prompt.

    cfg is taken in order to instruct "always judge whether there is/ isn't an
    impact on the holdings ($tickers)". Without cfg, qwen2.5:14b tends to settle
    every topic as "no impact on holdings".
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    return render(
        "local_section_geo_events",
        today=today,
        tickers=tickers,
        web_context=render_geo_events_block(ctx),
    )


def build_section_insight_prompt(
    cfg: BriefingConfig, *, prior_text: str, today: str
) -> str:
    """Prompt for generating the "implications for me" based on the A-C body.

    The insight section needs no URL citations (also stated in the system prompt),
    so web_context is not passed. Instead, the body summary of stages 1-3 is fed
    into `prior_text` for the model to reference.
    """
    themes = join_safe(cfg.portfolio.themes, sep=", ")
    return render(
        "local_section_insight",
        today=today,
        themes=themes,
        prior_text=prior_text,
    )


def load_local_briefing_system_prompt() -> str:
    """Strict instructions placed in the system role. Consolidates citation rules and output format."""
    return render("local_briefing_system")
