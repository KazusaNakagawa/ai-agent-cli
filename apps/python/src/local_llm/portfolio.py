"""Structured generation of the holdings table (#152).

Previously the entire table was generated as Markdown in a single chat() call,
but qwen2.5:14b would:
- fabricate plausible-looking URLs more than 50% of the time
- mix up sources across rows (e.g. an MSFT article on the NOC row)
- omit the heading / header / separator rows and break the table rendering

so instead we make one call per ticker using Ollama's structured outputs
(format=JSON schema) and have it emit only {topic, source_index}. The model
never writes a URL (the prompt only passes numbered titles), and sources are
resolved on the Python side against the pre-fetch (title, url). The price-move
cell is also filled from the real values in fetch_stock_move_map. Fabrication,
cross-contamination, and broken tables become structurally impossible.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from src.generator.prompt import render
from src.logger import get_logger

from .briefing import PrefetchedContext, _msg_field
from .search import SearchResult

logger = get_logger(__name__)

# JSON schema passed to Ollama structured outputs. source_index is "the number
# (1-based) of the search result it relied on"; null if none applies.
PORTFOLIO_ROW_FORMAT: dict = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "source_index": {"type": ["integer", "null"]},
    },
    "required": ["topic", "source_index"],
}

# Cap on the body excerpt put in the row prompt. The task is extracting "a
# one-line topic + source number", so the full text used for section generation
# (articles.MAX_ARTICLE_CHARS=1800) is unnecessary. Since chat() runs per ticker,
# the shorter it is the more latency is saved.
MAX_ROW_CONTENT_CHARS = 600

NO_NEWS_TOPIC = "(具体的なニュースは検索でも確認できず)"
GENERATION_ERROR_TOPIC = "(生成エラー — 構造化出力の解析に失敗)"

TABLE_HEADER = (
    "## 保有銘柄テーブル\n"
    "\n"
    "| 銘柄 | 値動き | 今日のトピック (1 行) | 出典 |\n"
    "|---|---|---|---|"
)


class _OllamaStructuredChatLike(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        format: dict | None = None,
    ) -> Any: ...


def render_numbered_hits(hits: list[SearchResult]) -> str:
    """Format search results with numbers. **URLs are intentionally omitted** (#152).

    The model cites by number, and resolution to URLs happens on the Python side.
    Not showing URLs is the key to making fabrication structurally impossible.
    """
    lines: list[str] = []
    for i, r in enumerate(hits, start=1):
        desc = r.description.strip().replace("\n", " ")
        if len(desc) > 200:
            desc = desc[:200] + "..."
        lines.append(f"{i}. {r.title} — {desc}")
        if r.content:
            content = r.content.strip().replace("\n", " ")
            if len(content) > MAX_ROW_CONTENT_CHARS:
                content = content[:MAX_ROW_CONTENT_CHARS] + "..."
            lines.append(f"   本文抜粋: {content}")
    return "\n".join(lines)


def build_row_prompt(ticker: str, hits: list[SearchResult], *, today: str) -> str:
    return render(
        "local_portfolio_row",
        today=today,
        ticker=ticker,
        numbered_hits=render_numbered_hits(hits),
    )


def _generate_row(
    ticker: str,
    hits: list[SearchResult],
    *,
    ollama_client: _OllamaStructuredChatLike,
    model: str,
    options: dict | None,
    today: str,
) -> tuple[str, int | None]:
    """Return (topic, source_index). Parse failures / out-of-range indexes fail safe."""
    prompt = build_row_prompt(ticker, hits, today=today)
    resp = ollama_client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options=options,
        format=PORTFOLIO_ROW_FORMAT,
    )
    msg = _msg_field(resp, "message")
    if msg is None:
        msg = resp
    content = _msg_field(msg, "content", "") or ""

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("[portfolio] %s: JSON parse failed: %s (raw=%r)", ticker, e, content[:200])
        return GENERATION_ERROR_TOPIC, None
    if not isinstance(data, dict):
        logger.warning("[portfolio] %s: JSON is not an object: %r", ticker, content[:200])
        return GENERATION_ERROR_TOPIC, None

    topic = str(data.get("topic") or "").strip() or NO_NEWS_TOPIC
    idx = data.get("source_index")
    if not isinstance(idx, int) or isinstance(idx, bool) or not (1 <= idx <= len(hits)):
        if idx is not None:
            logger.warning(
                "[portfolio] %s: source_index=%r out of range (hits=%d) — treating as no source",
                ticker,
                idx,
                len(hits),
            )
        idx = None
    return topic, idx


def _sanitize_cell(text: str) -> str:
    """Collapse `|` and newlines that would break the Markdown table."""
    return text.replace("|", " ").replace("\n", " ").strip()


def generate_portfolio_table(
    tickers: list[str],
    *,
    ctx: PrefetchedContext,
    moves: dict[str, str],
    ollama_client: _OllamaStructuredChatLike,
    model: str,
    options: dict | None = None,
    today: str,
) -> str:
    """Return the holdings table for all tickers as Markdown.

    Tickers with 0 search hits skip the LLM and immediately emit a "not
    confirmed" row (saving calls). The source cell resolves source_index to the
    pre-fetch (title, url) and links it on the Python side, so URL fabrication
    cannot occur.
    """
    rows = [TABLE_HEADER]
    for ticker in tickers:
        hits = ctx.per_ticker.get(ticker, [])
        move = _sanitize_cell(moves.get(ticker, "-")) or "-"

        if not hits:
            topic: str = NO_NEWS_TOPIC
            idx: int | None = None
        else:
            logger.info("[portfolio] %s: generating row (hits=%d)", ticker, len(hits))
            topic, idx = _generate_row(
                ticker,
                hits,
                ollama_client=ollama_client,
                model=model,
                options=options,
                today=today,
            )

        if idx is not None:
            src = hits[idx - 1]
            source = f"[{_sanitize_cell(src.title)}]({src.url})"
        else:
            source = "-"
        rows.append(f"| {ticker} | {move} | {_sanitize_cell(topic)} | {source} |")
    return "\n".join(rows)
