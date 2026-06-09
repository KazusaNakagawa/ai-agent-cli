"""Brave Search API クライアント。ローカル LLM のツールコールから呼ばれる。"""

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


class BraveSearchError(RuntimeError):
    pass


class BraveSearchClient:
    """Brave Search Web API の薄いラッパ。

    `api_key` は呼び出し側 (CLI) が env から読んで渡す。`http_client` は
    テストでスタブできるよう注入可能。
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

    def search(self, query: str, count: int = 5) -> list[SearchResult]:
        count = max(1, min(int(count), 10))
        params = {"q": query, "count": count}
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        if self._http is not None:
            resp = self._http.get(self._endpoint, params=params, headers=headers)
        else:
            resp = httpx.get(
                self._endpoint, params=params, headers=headers, timeout=self._timeout
            )
        if resp.status_code != 200:
            raise BraveSearchError(
                f"Brave Search returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
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
