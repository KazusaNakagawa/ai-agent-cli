"""Article body fetching and extraction (#151).

With only the pre-fetch snippet (title + ≤200 chars), a 14B-class model cannot
write concrete facts and ends up vaguely making things up or misattributing
sources. By actually fetching the URL of each topic's top hit, extracting the
body with trafilatura, truncating it, and injecting it into the prompt, the task
shifts from "inventing from a headline" to "summarizing the body".
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace
from typing import Any, Protocol

import httpx

from src.logger import get_logger

from .briefing import PrefetchedContext
from .search import SearchResult

logger = get_logger(__name__)


class _HttpGetLike(Protocol):
    """Minimal HTTP interface for test injection (httpx-compatible get only)."""

    def get(self, url: str, headers: dict | None = None) -> Any: ...


# Body cap per article. 8 tickers × 1 article × 1800 chars ≈ 7K tokens, a budget
# that fits within the section-split prompt + num_ctx 16K (#150).
MAX_ARTICLE_CHARS = 1800
# Macro is the foundation for every section, so 2 articles; everything else uses
# the top 1 hit per topic.
PER_MACRO_ARTICLES = 2
PER_GROUP_ARTICLES = 1

FETCH_TIMEOUT = 10.0
# Some news sites reject the default UA (python-httpx/...) with a 403.
_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _fetch_article_text(
    url: str, *, http_client: _HttpGetLike | None = None, max_chars: int = MAX_ARTICLE_CHARS
) -> str:
    """Fetch the URL and return the body as plain text. Empty string on failure (caller falls back to the snippet)."""
    try:
        if http_client is not None:
            resp = http_client.get(url, headers=_FETCH_HEADERS)
        else:
            resp = httpx.get(
                url,
                headers=_FETCH_HEADERS,
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
            )
    except Exception as e:
        logger.warning("[articles] fetch failed for %s: %s", url, e)
        return ""
    if resp.status_code != 200:
        logger.warning("[articles] HTTP %d for %s", resp.status_code, url)
        return ""

    try:
        import trafilatura

        text = trafilatura.extract(resp.text) or ""
    except Exception as e:
        logger.warning("[articles] extract failed for %s: %s", url, e)
        return ""

    text = " ".join(text.split())  # collapse newlines / runs of whitespace into one line
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return text


def _enrich_results(
    results: list[SearchResult],
    n: int,
    *,
    http_client: _HttpGetLike | None,
    max_chars: int,
) -> list[SearchResult]:
    out: list[SearchResult] = []
    for i, r in enumerate(results):
        if i < n and r.url:
            text = _fetch_article_text(
                r.url, http_client=http_client, max_chars=max_chars
            )
            out.append(replace(r, content=text) if text else r)
        else:
            out.append(r)
    return out


def enrich_with_article_text(
    ctx: PrefetchedContext,
    *,
    http_client: _HttpGetLike | None = None,
    per_macro: int = PER_MACRO_ARTICLES,
    per_group: int = PER_GROUP_ARTICLES,
    max_chars: int = MAX_ARTICLE_CHARS,
) -> PrefetchedContext:
    """Return a new ctx with each group's top hits' article bodies fetched into content.

    Hits whose fetch/extraction fails are left with their snippet (the whole run
    is not aborted). `http_client` is the test injection point (must have
    get(url, headers=...)).
    """
    # Rebuild via dataclasses.replace so that new PrefetchedContext fields are not
    # silently dropped (Sourcery feedback).
    enriched = dataclasses.replace(
        ctx,
        macro=_enrich_results(
            ctx.macro, per_macro, http_client=http_client, max_chars=max_chars
        ),
        per_ticker={
            t: _enrich_results(
                hits, per_group, http_client=http_client, max_chars=max_chars
            )
            for t, hits in ctx.per_ticker.items()
        },
        geo_by_topic={
            topic: _enrich_results(
                hits, per_group, http_client=http_client, max_chars=max_chars
            )
            for topic, hits in ctx.geo_by_topic.items()
        },
        events_by_name={
            name: _enrich_results(
                hits, per_group, http_client=http_client, max_chars=max_chars
            )
            for name, hits in ctx.events_by_name.items()
        },
    )
    attempted, fetched = count_article_fetches(enriched, per_macro=per_macro, per_group=per_group)
    logger.info("[articles] fetched bodies for %d/%d", fetched, attempted)
    return enriched


def count_article_fetches(
    ctx: PrefetchedContext,
    *,
    per_macro: int = PER_MACRO_ARTICLES,
    per_group: int = PER_GROUP_ARTICLES,
) -> tuple[int, int]:
    """Return (attempted count, count with content filled). For caveat-line transparency."""
    attempted = 0
    fetched = 0

    def _count(results: list[SearchResult], n: int) -> None:
        nonlocal attempted, fetched
        for r in results[:n]:
            if not r.url:
                continue
            attempted += 1
            if r.content:
                fetched += 1

    _count(ctx.macro, per_macro)
    for hits in ctx.per_ticker.values():
        _count(hits, per_group)
    for hits in ctx.geo_by_topic.values():
        _count(hits, per_group)
    for hits in ctx.events_by_name.values():
        _count(hits, per_group)
    return attempted, fetched
