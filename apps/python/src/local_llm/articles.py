"""記事本文の取得と抽出 (#151)。

pre-fetch のスニペット (タイトル + ≤200 字) だけでは 14B クラスのモデルは
具体的事実を書けず、曖昧な作文や出典ズレが起きる。各トピック上位ヒットの
URL を実際に fetch して trafilatura で本文抽出し、切り詰めてプロンプトに
注入することで、タスクを「見出しからの創作」から「本文の要約」に変える。
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
    """テスト注入用の最小 HTTP インターフェース (httpx 互換の get のみ)。"""

    def get(self, url: str, headers: dict | None = None) -> Any: ...


# 1 記事あたりの本文上限。8 銘柄 × 1 記事 × 1800 字 ≒ 7K tokens で、セクション
# 分割プロンプト + num_ctx 16K (#150) に収まる予算。
MAX_ARTICLE_CHARS = 1800
# マクロは全セクションの土台になるので 2 件、その他はトピックごと上位 1 件。
PER_MACRO_ARTICLES = 2
PER_GROUP_ARTICLES = 1

FETCH_TIMEOUT = 10.0
# 一部のニュースサイトはデフォルト UA (python-httpx/...) を 403 で弾く。
_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _fetch_article_text(
    url: str, *, http_client: _HttpGetLike | None = None, max_chars: int = MAX_ARTICLE_CHARS
) -> str:
    """URL を fetch して本文をプレーンテキストで返す。失敗は空文字 (呼び出し側でスニペットにフォールバック)。"""
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

    text = " ".join(text.split())  # 改行・連続空白を畳んで 1 行に
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
    """各グループ上位ヒットの記事本文を取得して content に埋めた新 ctx を返す。

    fetch/抽出に失敗したヒットはスニペットのまま残す (全体は止めない)。
    `http_client` はテスト用注入ポイント (get(url, headers=...) を持つこと)。
    """
    # PrefetchedContext にフィールドが増えても黙って欠落しないよう
    # dataclasses.replace で再構築する (Sourcery 指摘)。
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
    logger.info("[articles] 本文取得 %d/%d 件成功", fetched, attempted)
    return enriched


def count_article_fetches(
    ctx: PrefetchedContext,
    *,
    per_macro: int = PER_MACRO_ARTICLES,
    per_group: int = PER_GROUP_ARTICLES,
) -> tuple[int, int]:
    """(試行件数, content が埋まった件数) を返す。caveat 行の透明性用。"""
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
