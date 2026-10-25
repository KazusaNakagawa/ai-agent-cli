"""Render a validated BriefScript holdings section to the briefing's Markdown.

Every figure in a heading comes from fetcher quotes; the LLM's claims are only
ever rendered as bullet text, so nothing it writes can stand in for a price or
a move. Claim and source text is model output informed by arbitrary web pages,
so it is flattened before it reaches Discord / Notion: no headings, links or
mentions survive from it.
"""
from __future__ import annotations

import dataclasses
import re

from src.fetcher.stocks import StockQuote, _currency_symbol, to_jpy_change_pct
from src.generator.briefscript_schema import (
    BriefingDocument,
    Claim,
    HoldingsBlock,
    HoldingsSection,
    MarketSnapshot,
    QuoteSnapshot,
)

HOLDINGS_HEADING = "### 自分への示唆"

# Markers that keep a non-confirmed claim from reading as fact.
_CONFIDENCE_MARKERS = {"confirmed": "", "inferred": "〔推測〕", "unknown": "〔未確認〕"}

# Bullet for a configured holding the LLM returned nothing for.
_MISSING_NOTE = "〔未確認〕今日の材料は確認できませんでした。"
# Bullet for every holding when the BriefScript call failed outright.
_FAILED_NOTE = "〔未確認〕本日の示唆は生成できませんでした。"

_LEADING_HASHES = re.compile(r"^\s*#+\s*")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_REF_LINK = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")
# Autolinks (<https://...>) and bare URLs; Discord and Notion make both clickable.
_URL = re.compile(r"<https?://[^>\s]*>|https?://\S+")
_URL_PLACEHOLDER = "（URL 省略）"
# @everyone / @here and Discord's <@id>, <@!id>, <@&role>, <#channel> forms.
_MENTION = re.compile(r"@(everyone|here)\b|<([@#][!&]?)(\d+)>")

_SOURCES_HEADING = "**出典**"

# End of the holdings section: a ``---`` rule or an H3. CommonMark allows up to
# three leading spaces on both; four or more is an indented code block.
_SECTION_BOUNDARY = re.compile(r"^ {0,3}(?:---\s*$|### )")
# Opening/closing code fence; boundaries inside a fence are content, not structure.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _arrow(pct: float) -> str:
    # Same convention as the fetcher's text block: zero counts as down.
    return "↑" if pct > 0 else "↓"


def _heading(ticker: str, quote: StockQuote | None, fx_change_pct: float | None) -> str:
    if quote is None or quote.error or quote.last_price is None or quote.change_pct is None:
        return f"#### {ticker}：株価取得失敗"
    price = f"（{_currency_symbol(quote.currency)}{quote.last_price:.2f}）"
    move = f"{_arrow(quote.change_pct)}{abs(quote.change_pct):.1f}%"
    if quote.currency != "USD":
        return f"#### {ticker}：{move}{price}"
    if fx_change_pct is None:
        return f"#### {ticker}：ドル建て {move}{price}"
    jpy = to_jpy_change_pct(quote.change_pct, fx_change_pct)
    return f"#### {ticker}：ドル建て {move} / 円建て {_arrow(jpy)}{abs(jpy):.1f}%{price}"


def _plain(text: str) -> str:
    """One line of inert text: no heading marks, links or live mentions."""
    text = " ".join(text.split())
    text = _LEADING_HASHES.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _REF_LINK.sub(r"\1", text)
    # Claims cite sources by id; a URL in the text would bypass the source list.
    text = _URL.sub(_URL_PLACEHOLDER, text)
    # A full-width ＠ reads the same but Discord does not resolve it.
    return _MENTION.sub(
        lambda m: f"＠{m[1]}" if m[1] else f"{m[2].replace('@', '＠')}{m[3]}", text,
    )


def _bullet(claim: Claim, numbers: dict[str, int]) -> str:
    refs = "".join(f"［{numbers[sid]}］" for sid in claim.source_ids)
    return f"- {_CONFIDENCE_MARKERS[claim.confidence]}{_plain(claim.text)}{refs}"


def _unique(tickers: list[str]) -> list[str]:
    return list(dict.fromkeys(t.strip() for t in tickers if t.strip()))


def render_holdings_markdown(
    section: HoldingsSection,
    quotes: dict[str, StockQuote],
    tickers: list[str],
    fx_change_pct: float | None = None,
    missing_note: str = _MISSING_NOTE,
) -> str:
    """Render one ``####`` block per configured ticker, in configured order.

    Cited sources are numbered in order of first citation, marked ［n］ on
    the claims that cite them, and listed after the last holding.
    """
    notes = {note.ticker: note for note in section.holdings}
    tickers = _unique(tickers)
    numbers: dict[str, int] = {}
    for ticker in tickers:
        for claim in notes[ticker].claims if ticker in notes else ():
            for sid in claim.source_ids:
                numbers.setdefault(sid, len(numbers) + 1)

    blocks = []
    for ticker in tickers:
        note = notes.get(ticker)
        if note is None:
            bullets = [f"- {missing_note}"]
        else:
            bullets = [_bullet(c, numbers) for c in note.claims]
            if note.next_event:
                bullets.append(f"- 次の予定：{_plain(note.next_event)}")
        blocks.append("\n".join([_heading(ticker, quotes.get(ticker), fx_change_pct), *bullets]))

    by_id = {source.id: source for source in section.sources}
    if numbers:
        listed = [
            f"- ［{n}］[{_link_text(by_id[sid].title)}]({by_id[sid].url})"
            for sid, n in sorted(numbers.items(), key=lambda kv: kv[1])
        ]
        blocks.append("\n".join([_SOURCES_HEADING, *listed]))
    return "\n\n".join(blocks)


def render_holdings_fallback(
    quotes: dict[str, StockQuote],
    tickers: list[str],
    fx_change_pct: float | None = None,
) -> str:
    """Quote-derived headings only, for when the BriefScript call failed."""
    return render_holdings_markdown(
        HoldingsSection(holdings=[]), quotes, tickers, fx_change_pct, missing_note=_FAILED_NOTE,
    )


def _link_text(title: str) -> str:
    # Brackets would let a title close its own link and open another.
    return _plain(title).replace("[", "［").replace("]", "］")


def _section_end(lines: list[str], begin: int) -> int:
    """Index of the first boundary line at or after ``begin``, skipping fences."""
    fence: str | None = None
    for i in range(begin, len(lines)):
        m = _FENCE.match(lines[i])
        if fence is None:
            if m:
                fence = m[1]
            elif _SECTION_BOUNDARY.match(lines[i]):
                return i
        elif m and m[1][0] == fence[0] and len(m[1]) >= len(fence):
            fence = None
    return len(lines)


def split_holdings(body: str) -> tuple[str, str] | None:
    """Text before and after the holdings body, or None if the heading is absent.

    The section runs from its heading to the next ``---`` rule or ``### ``
    heading, whichever comes first. ``head`` ends with the heading and a blank
    line; ``tail`` restores the spacing before whatever followed.
    """
    lines = body.split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == HOLDINGS_HEADING)
    except StopIteration:
        return None
    end = _section_end(lines, start + 1)
    head = "\n".join(lines[: start + 1]) + "\n\n"
    rest = lines[end:]
    return head, "\n\n" + "\n".join(rest) if rest else "\n"


def splice_holdings(body: str, holdings_md: str) -> str | None:
    """Replace the body of the holdings section, or return None if it is absent."""
    parts = split_holdings(body)
    if parts is None:
        return None
    head, tail = parts
    return head + holdings_md + tail


def snapshot_market(
    quotes: dict[str, StockQuote] | None, fx_change_pct: float | None,
) -> MarketSnapshot:
    """Freeze fetcher quotes into the document, so it re-renders offline."""
    return MarketSnapshot(
        quotes=[QuoteSnapshot(**dataclasses.asdict(q)) for q in (quotes or {}).values()],
        fx_change_pct=fx_change_pct,
    )


def _render_holdings_block(block: HoldingsBlock, market: MarketSnapshot) -> str:
    quotes = {q.ticker: StockQuote(**q.model_dump()) for q in market.quotes}
    if block.content is None:
        return render_holdings_fallback(quotes, block.tickers, market.fx_change_pct)
    return render_holdings_markdown(block.content, quotes, block.tickers, market.fx_change_pct)


def render_document_markdown(doc: BriefingDocument) -> str:
    """The briefing Markdown that Discord, Notion and the local file receive."""
    parts = []
    for section in doc.sections:
        if isinstance(section, HoldingsBlock):
            parts.append(_render_holdings_block(section, doc.market))
        else:
            parts.append(section.text)
    return "".join(parts)
