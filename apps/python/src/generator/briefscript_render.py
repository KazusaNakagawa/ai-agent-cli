"""Render a validated BriefScript holdings section to the briefing's Markdown.

Every figure in a heading comes from fetcher quotes; the LLM's claims are only
ever rendered as bullet text, so nothing it writes can stand in for a price or
a move.
"""
from __future__ import annotations

import re

from src.fetcher.stocks import StockQuote, _currency_symbol, to_jpy_change_pct
from src.generator.briefscript_schema import Claim, HoldingsSection

HOLDINGS_HEADING = "### 自分への示唆"

# Markers that keep a non-confirmed claim from reading as fact.
_CONFIDENCE_MARKERS = {"confirmed": "", "inferred": "〔推測〕", "unknown": "〔未確認〕"}

# Bullet for a configured holding the LLM returned nothing for.
_MISSING_NOTE = "〔未確認〕今日の材料は確認できませんでした。"

_LEADING_HASHES = re.compile(r"^\s*#+\s*")


def _arrow(pct: float) -> str:
    # Same convention as the fetcher's text block: zero counts as down.
    return "↑" if pct > 0 else "↓"


def _heading(ticker: str, quote: StockQuote | None, fx_change_pct: float | None) -> str:
    if quote is None or quote.error:
        return f"#### {ticker}：株価取得失敗"
    price = f"（{_currency_symbol(quote.currency)}{quote.last_price:.2f}）"
    move = f"{_arrow(quote.change_pct)}{abs(quote.change_pct):.1f}%"
    if quote.currency != "USD":
        return f"#### {ticker}：{move}{price}"
    if fx_change_pct is None:
        return f"#### {ticker}：ドル建て {move}{price}"
    jpy = to_jpy_change_pct(quote.change_pct, fx_change_pct)
    return f"#### {ticker}：ドル建て {move} / 円建て {_arrow(jpy)}{abs(jpy):.1f}%{price}"


def _bullet(claim: Claim) -> str:
    # One line, no leading heading marks: claim text must stay inside its bullet.
    text = " ".join(claim.text.split())
    text = _LEADING_HASHES.sub("", text)
    return f"- {_CONFIDENCE_MARKERS[claim.confidence]}{text}"


def render_holdings_markdown(
    section: HoldingsSection,
    quotes: dict[str, StockQuote],
    tickers: list[str],
    fx_change_pct: float | None = None,
) -> str:
    """Render one ``####`` block per configured ticker, in configured order."""
    notes = {note.ticker: note for note in section.holdings}
    blocks = []
    for ticker in tickers:
        note = notes.get(ticker)
        bullets = [_bullet(c) for c in note.claims] if note else [f"- {_MISSING_NOTE}"]
        blocks.append("\n".join([_heading(ticker, quotes.get(ticker), fx_change_pct), *bullets]))
    return "\n\n".join(blocks)


def splice_holdings(body: str, holdings_md: str) -> str | None:
    """Replace the body of the holdings section, or return None if it is absent.

    The section runs from its heading to the next ``---`` rule or ``### ``
    heading, whichever comes first.
    """
    lines = body.split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == HOLDINGS_HEADING)
    except StopIteration:
        return None
    end = next(
        (i for i in range(start + 1, len(lines))
         if lines[i].strip() == "---" or lines[i].startswith("### ")),
        len(lines),
    )
    tail = lines[end:]
    replaced = [*lines[: start + 1], "", holdings_md, ""]
    return "\n".join(replaced + tail) if tail else "\n".join(replaced[:-1]) + "\n"
