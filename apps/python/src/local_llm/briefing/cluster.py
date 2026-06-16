"""Cluster pre-fetched news hits into themes before section generation (#169).

Pre-fetch queries macro + every ticker separately, so the same story (e.g. a Fed
decision or a chip-export rule) shows up as duplicate hits across several tickers
and the macro query. Feeding those raw per-query lists into the top-news prompt
makes the model emit the same story several times. This module collapses
overlapping hits into distinct ``NewsCluster`` stories before generation.

Clustering is two-pass:
1. Exact URL dedup — the same URL fetched under macro and a ticker becomes one
   cluster, merging the source tags.
2. Similarity grouping — remaining hits are greedily attached to an existing
   cluster when similar enough. Similarity is pluggable: pass ``embed_fn`` to use
   bge-m3 embeddings (cosine); the default is an offline, deterministic
   token-Jaccard heuristic over title+description so the pipeline (and tests) run
   without Ollama.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from ..search import SearchResult
from .prefetch import PrefetchedContext

# Tokenizer for the heuristic similarity: lowercase alnum runs, length >= 2 so
# single-char noise and most punctuation drop out.
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

# Default Jaccard threshold to treat two hits as the same story. Tuned to merge
# clear restatements (shared tickers/keywords) without collapsing distinct
# stories that merely share a company name.
DEFAULT_SIMILARITY_THRESHOLD = 0.5

# Caps for the rendered block so a verbose article body doesn't bloat the prompt.
_MAX_DESC_CHARS = 200
_MAX_CONTENT_CHARS = 500

EmbedFn = Callable[[list[str]], list[list[float]]]


@dataclass
class NewsCluster:
    """A single deduplicated news story drawn from one or more pre-fetch hits.

    ``results`` keeps every member hit (the first is the representative); ``sources``
    records which pre-fetch queries surfaced the story ("macro" or a ticker), so the
    prompt can show "this story touches PLTR + NVDA" rather than listing it twice.
    """

    results: list[SearchResult] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def primary(self) -> SearchResult:
        return self.results[0]

    def add(self, result: SearchResult, source: str) -> None:
        self.results.append(result)
        if source not in self.sources:
            self.sources.append(source)

    def merge_from(self, other: "NewsCluster") -> None:
        """Absorb another cluster's member hits and source tags."""
        self.results.extend(other.results)
        for source in other.sources:
            if source not in self.sources:
                self.sources.append(source)


def _clip(text: str | None, limit: int) -> str:
    """Flatten newlines and truncate to ``limit`` chars (with an ellipsis)."""
    flat = (text or "").strip().replace("\n", " ")
    return flat[:limit] + "..." if len(flat) > limit else flat


def _text_of(result: SearchResult) -> str:
    return f"{result.title} {result.description}".strip()


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(
            f"cosine similarity requires equal-length vectors, got {len(a)} and {len(b)} "
            "(check embed_fn output dimensionality)"
        )
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _iter_tagged_hits(ctx: PrefetchedContext) -> list[tuple[str, SearchResult]]:
    """macro + per_ticker hits as (source_tag, result), in a stable order.

    geo/events are intentionally excluded: they are already distinct per-topic and
    feed their own section (#169 targets top-news cross-ticker/macro duplication).
    """
    tagged: list[tuple[str, SearchResult]] = [("macro", r) for r in ctx.macro]
    for ticker, hits in ctx.per_ticker.items():
        for r in hits:
            tagged.append((ticker, r))
    return tagged


def cluster_news_hits(
    ctx: PrefetchedContext,
    *,
    embed_fn: EmbedFn | None = None,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[NewsCluster]:
    """Group macro + per_ticker hits into deduplicated ``NewsCluster`` stories.

    ``embed_fn`` maps a list of texts to embedding vectors (e.g. bge-m3 via Ollama);
    when omitted, a deterministic token-Jaccard heuristic is used so the step runs
    offline. ``threshold`` is the minimum similarity (cosine or Jaccard) to merge a
    hit into an existing cluster.
    """
    tagged = _iter_tagged_hits(ctx)
    if not tagged:
        return []

    # Pass 1: exact URL dedup. Same URL across sources collapses to one cluster.
    by_url: dict[str, NewsCluster] = {}
    deduped: list[tuple[str, SearchResult]] = []
    for source, result in tagged:
        existing = by_url.get(result.url)
        if existing is not None:
            existing.add(result, source)
            continue
        cluster = NewsCluster()
        cluster.add(result, source)
        by_url[result.url] = cluster
        deduped.append((source, result))

    clusters = [by_url[result.url] for _, result in deduped]

    # Pass 2: similarity grouping over the URL-unique representatives.
    if embed_fn is not None:
        vectors = embed_fn([_text_of(r) for _, r in deduped])
        if len(vectors) != len(deduped):
            raise ValueError(
                f"embed_fn must return one vector per text, got {len(vectors)} "
                f"for {len(deduped)} inputs"
            )

        def sim(i: int, j: int) -> float:
            return _cosine(vectors[i], vectors[j])
    else:
        token_sets = [_tokens(_text_of(r)) for _, r in deduped]

        def sim(i: int, j: int) -> float:
            return _jaccard(token_sets[i], token_sets[j])

    merged: list[int] = []  # indices of surviving cluster representatives
    parent: dict[int, int] = {}  # absorbed index -> surviving index
    for i in range(len(deduped)):
        target = None
        for j in merged:
            if sim(i, j) >= threshold:
                target = j
                break
        if target is None:
            merged.append(i)
        else:
            parent[i] = target

    result_clusters: list[NewsCluster] = []
    index_of_survivor: dict[int, int] = {}
    for pos, i in enumerate(merged):
        index_of_survivor[i] = pos
        result_clusters.append(clusters[i])
    for absorbed, survivor in parent.items():
        target = result_clusters[index_of_survivor[survivor]]
        target.merge_from(clusters[absorbed])
    return result_clusters


def render_clusters_block(clusters: list[NewsCluster]) -> str:
    """Render clustered stories as the top-news search-result block.

    Each cluster is one bullet (representative title/url + which tickers/macro it
    touches), with any additional member links and body excerpts nested below, so
    the model sees one deduplicated story instead of per-query repeats.
    """
    if not clusters:
        return "### クラスタ済みニュース\n  - (検索ヒットなし)"
    lines = ["### クラスタ済みニュース"]
    for c in clusters:
        primary = c.primary
        desc = _clip(primary.description, _MAX_DESC_CHARS)
        srcs = "、".join(c.sources) if c.sources else "-"
        lines.append(f"  - [{primary.title}]({primary.url}) — {desc}")
        lines.append(f"    - 関連: {srcs}")
        if primary.content:
            lines.append(f"    - 本文抜粋: {_clip(primary.content, _MAX_CONTENT_CHARS)}")
        for extra in c.results[1:]:
            lines.append(f"    - 関連記事: [{extra.title}]({extra.url})")
    return "\n".join(lines)
