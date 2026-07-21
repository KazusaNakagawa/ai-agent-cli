"""Brave Search pre-fetch and its container.

#144 pre-fetch: qwen2.5:14b's tool-calling is unreliable (it only searches 2 of 8
tickers), so the Python side always web_searches every item and injects it into
the prompt. The tool path is retired.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.config import BriefingConfig
from src.logger import get_logger

from ..search import BraveSearchClient, BraveSearchError, SearchResult
from .filters import _extract_url_date, _is_index_page, _url_has_no_spaces

logger = get_logger(__name__)


PER_TICKER_RESULTS = 3
PER_MACRO_RESULTS = 3
PER_GEO_RESULTS = 2
PER_EVENT_RESULTS = 2

# Brave's recency filter. Daily briefing, so limit to the last 1 week (#153).
PREFETCH_FRESHNESS = "pw"
# Brave's freshness is a hint and can still return articles older than this.
# When a URL date is available, the Python side drops articles older than this many days.
STALE_ARTICLE_DAYS = 7
# Extra over-fetch count to account for what the index-page filter prunes.
# Brave's count cap is 10 (clamped client-side). The current PER_* max is 3, so
# 3+3=6 stays within range, but if you raise PER_* take care not to exceed 10.
OVERFETCH_EXTRA = 3


@dataclass(frozen=True)
class PrefetchedContext:
    """Bundle of pre-fetched web_search results, for injection into the prompt.

    geo_by_topic / events_by_name are the result of querying every entry in
    briefing.json one at a time. They were made multi-result from #144 onward to
    make up for low coverage relative to the Claude path (geo had only the first
    hit; events were not fetched at all).
    """

    macro: list[SearchResult]
    per_ticker: dict[str, list[SearchResult]]
    geo_by_topic: dict[str, list[SearchResult]]
    events_by_name: dict[str, list[SearchResult]]

    @property
    def allowed_urls(self) -> set[str]:
        """Whitelist for URL validation. The full set of URLs obtained by pre-fetch."""
        urls: set[str] = set()
        for r in self.macro:
            urls.add(r.url)
        for hits in self.per_ticker.values():
            for r in hits:
                urls.add(r.url)
        for hits in self.geo_by_topic.values():
            for r in hits:
                urls.add(r.url)
        for hits in self.events_by_name.values():
            for r in hits:
                urls.add(r.url)
        return urls


def _safe_search(
    client: BraveSearchClient,
    query: str,
    count: int,
    *,
    reference_date: date | None = None,
) -> list[SearchResult]:
    """web_search with freshness=pw + index-page / stale-article filters (#153).

    Brave's freshness is a ranking hint and can return old articles. If
    reference_date is given, articles whose URL date can be extracted are dropped
    when older than STALE_ARTICLE_DAYS. Over-fetch OVERFETCH_EXTRA extra so count
    results remain even after filtering, then truncate to count. Failure returns
    an empty list (other queries continue).
    """
    try:
        hits = client.search(
            query, count=count + OVERFETCH_EXTRA, freshness=PREFETCH_FRESHNESS
        )
    except BraveSearchError as e:
        logger.warning("[prefetch] web_search failed for %r: %s", query, e)
        return []
    kept = []
    n_index = n_malformed = n_stale = 0
    for r in hits:
        if _is_index_page(r.url):
            n_index += 1
        elif not _url_has_no_spaces(r.url):
            n_malformed += 1
        elif reference_date is not None:
            article_date = _extract_url_date(r.url)
            if article_date is not None and (reference_date - article_date).days > STALE_ARTICLE_DAYS:
                n_stale += 1
            else:
                kept.append(r)
        else:
            kept.append(r)
    if n_index:
        logger.info("[prefetch] %r: excluded %d index pages", query, n_index)
    if n_malformed:
        logger.info("[prefetch] %r: excluded %d malformed URLs (with spaces)", query, n_malformed)
    if n_stale:
        logger.info("[prefetch] %r: excluded %d stale articles (>%d days)", query, n_stale, STALE_ARTICLE_DAYS)
    return kept[:count]


def prefetch_briefing_context(
    cfg: BriefingConfig,
    *,
    search_client: BraveSearchClient,
    today: str,
) -> PrefetchedContext:
    """Reliably web_search macro + every ticker + every conflict + every watch_event.

    Leaving tool calling to the model produces gaps such as searching only 2 of 8
    tickers, so the Python side guarantees coverage. Each query stays within the
    Brave Free plan's safe limits (max 1 QPS, 2000/month). The daily query count is
    about ``1 + len(tickers) + len(conflicts) + len(events)``; a typical
    briefing.json (10 tickers + 5 conflicts + 5 events) is 21 queries/day =
    630/month, within budget.
    """
    ref_date = date.fromisoformat(today)
    macro = _safe_search(
        search_client, f"stock market news {today}", PER_MACRO_RESULTS, reference_date=ref_date
    )
    logger.info("[prefetch] macro hits=%d", len(macro))

    per_ticker: dict[str, list[SearchResult]] = {}
    for ticker in cfg.portfolio.tickers:
        # Spelling out the date in the query makes that day's market articles hit
        # rather than Yahoo Finance / Robinhood ticker index pages (generic SEO top results).
        hits = _safe_search(
            search_client, f"{ticker} stock news {today}", PER_TICKER_RESULTS,
            reference_date=ref_date,
        )
        per_ticker[ticker] = hits
        logger.info("[prefetch] ticker=%s hits=%d", ticker, len(hits))

    geo_by_topic: dict[str, list[SearchResult]] = {}
    for conflict in getattr(cfg.geopolitical, "conflicts", None) or []:
        name = getattr(conflict, "name", None) or ""
        if not name:
            continue
        # With the Japanese topic name as-is, evergreen topic index pages and book
        # pages rank at the top. If briefing.json has query_en, use the English
        # news query (#153).
        query_en = getattr(conflict, "query_en", None) or ""
        query = f"{query_en} latest news" if query_en else f"{name} today"
        hits = _safe_search(search_client, query, PER_GEO_RESULTS, reference_date=ref_date)
        geo_by_topic[name] = hits
        logger.info("[prefetch] geo topic=%r query=%r hits=%d", name, query, len(hits))

    events_by_name: dict[str, list[SearchResult]] = {}
    for event in getattr(cfg, "watch_events", None) or []:
        name = getattr(event, "name", None) or ""
        if not name:
            continue
        trigger = getattr(event, "trigger", None) or ""
        query = f"{name} {trigger}".strip() if trigger else f"{name} news"
        hits = _safe_search(search_client, query, PER_EVENT_RESULTS, reference_date=ref_date)
        events_by_name[name] = hits
        logger.info("[prefetch] event=%r hits=%d", name, len(hits))

    return PrefetchedContext(
        macro=macro,
        per_ticker=per_ticker,
        geo_by_topic=geo_by_topic,
        events_by_name=events_by_name,
    )
