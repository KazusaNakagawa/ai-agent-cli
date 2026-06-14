"""Brave Search API client. Called from the local LLM's tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from src.logger import get_logger

logger = get_logger(__name__)

BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    description: str
    # Article body excerpt (#151). Empty at search time;
    # articles.enrich_with_article_text fills it in later for top hits only.
    # Extra context, because the model cannot write concrete facts from the
    # snippet (description ≤200 chars) alone.
    content: str = ""


class BraveSearchError(RuntimeError):
    pass


class BraveSearchClient:
    """Thin wrapper around the Brave Search Web API.

    `api_key` is read from env by the caller (CLI) and passed in. `http_client`
    is injectable so it can be stubbed in tests.
    """

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = BRAVE_SEARCH_ENDPOINT,
        http_client: Any | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not api_key:
            raise BraveSearchError("BRAVE_API_KEY is empty")
        self._api_key = api_key
        self._endpoint = endpoint
        self._http = http_client
        self._timeout = timeout

    def search(
        self, query: str, count: int = 5, freshness: str | None = None
    ) -> list[SearchResult]:
        """`freshness` is Brave's recency filter (pd=24h / pw=1 week / pm=1 month).

        The daily briefing pre-fetch tends to surface topic index pages
        (evergreen SEO-ranked pages), so callers generally pass "pw" (#153).
        """
        count = max(1, min(int(count), 10))
        params: dict[str, Any] = {"q": query, "count": count}
        if freshness:
            params["freshness"] = freshness
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        try:
            if self._http is not None:
                resp = self._http.get(self._endpoint, params=params, headers=headers)
            else:
                resp = httpx.get(
                    self._endpoint, params=params, headers=headers, timeout=self._timeout
                )
        except Exception as e:
            raise BraveSearchError(f"Brave Search request failed: {e}") from e
        if resp.status_code != 200:
            raise BraveSearchError(
                f"Brave Search returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise BraveSearchError(f"Brave Search response is not valid JSON: {e}") from e
        items = (data.get("web") or {}).get("results") or []
        out: list[SearchResult] = []
        for it in items[:count]:
            r = SearchResult(
                title=str(it.get("title", "")),
                url=str(it.get("url", "")),
                description=str(it.get("description", "")),
            )
            out.append(r)
            logger.debug(
                "[brave] q=%r -> title=%r url=%s desc=%s",
                query,
                r.title,
                r.url,
                r.description[:120].replace("\n", " "),
            )
        return out
