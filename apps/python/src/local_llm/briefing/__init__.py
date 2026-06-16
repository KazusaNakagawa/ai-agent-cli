"""Briefing generation for the local LLM.

A package that splits prompt assembly, search pre-fetch, the Ollama call, and MD
composition by responsibility. For backward compatibility it re-exports here all
the public symbols that used to be referenced from `src.local_llm.briefing`.

Design notes:
- #144 pre-fetch: qwen2.5:14b's tool-calling is unreliable (it only searches 2 of
  8 tickers), so the Python side always web_searches every item and injects it
  into the prompt. The tool path is retired.
- Section split: generating all 9 sections in a single chat() scatters attention
  and caused frequent URL fabrication in places like the holdings table. Splitting
  into stages and narrowing web_context to just that section's portion stabilizes
  citation following. The holdings table is separated into portfolio.py's
  structured-output path (#152).

Module layout:
- filters:  filter / extraction helpers for URLs, dates, index pages, Simplified Chinese
- prefetch: Brave Search pre-fetch and PrefetchedContext
- render:   rendering of search-result blocks / summary / debug / references
- prompts:  per-section prompt construction / system prompt
- generate: single-shot Ollama generation
- validate: URL whitelist matching
- compose:  final Markdown composition with the caveat header
"""

from __future__ import annotations

from .cluster import (
    DEFAULT_SIMILARITY_THRESHOLD,
    NewsCluster,
    cluster_news_hits,
    render_clusters_block,
)
from .compose import compose_briefing_md
from .filters import (
    _extract_url_date,
    _is_index_page,
    _trim_md_link_closer,
    _url_has_no_spaces,
    _URL_RE,
    has_simplified_chinese_text,
)
from .generate import (
    _CHARS_PER_TOKEN_ESTIMATE,
    _OllamaChatLike,
    _msg_field,
    generate_local_briefing,
)
from .prefetch import (
    OVERFETCH_EXTRA,
    PER_EVENT_RESULTS,
    PER_GEO_RESULTS,
    PER_MACRO_RESULTS,
    PER_TICKER_RESULTS,
    PREFETCH_FRESHNESS,
    STALE_ARTICLE_DAYS,
    PrefetchedContext,
    _safe_search,
    prefetch_briefing_context,
)
from .prompts import (
    build_section_geo_events_prompt,
    build_section_insight_prompt,
    build_section_sector_prompt,
    build_section_topnews_prompt,
    load_local_briefing_system_prompt,
)
from .render import (
    _format_results,
    collect_references,
    ensure_geo_topics_covered,
    render_geo_events_block,
    render_macro_block,
    render_prefetch_debug_block,
    summarize_prefetch_hits,
)
from .validate import UrlValidation, validate_urls

__all__ = [
    "DEFAULT_SIMILARITY_THRESHOLD",
    "NewsCluster",
    "OVERFETCH_EXTRA",
    "PER_EVENT_RESULTS",
    "PER_GEO_RESULTS",
    "PER_MACRO_RESULTS",
    "PER_TICKER_RESULTS",
    "PREFETCH_FRESHNESS",
    "STALE_ARTICLE_DAYS",
    "PrefetchedContext",
    "UrlValidation",
    "build_section_geo_events_prompt",
    "build_section_insight_prompt",
    "build_section_sector_prompt",
    "build_section_topnews_prompt",
    "cluster_news_hits",
    "collect_references",
    "compose_briefing_md",
    "render_clusters_block",
    "ensure_geo_topics_covered",
    "generate_local_briefing",
    "has_simplified_chinese_text",
    "load_local_briefing_system_prompt",
    "prefetch_briefing_context",
    "render_geo_events_block",
    "render_macro_block",
    "render_prefetch_debug_block",
    "summarize_prefetch_hits",
    "validate_urls",
]
