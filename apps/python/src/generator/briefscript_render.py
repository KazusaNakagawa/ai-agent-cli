"""Render validated BriefScript sections to the briefing's Markdown.

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
    MainBlock,
    MainSection,
    MarketSnapshot,
    QuoteSnapshot,
    SectorsBlock,
    SectorsSection,
    Source,
)

HOLDINGS_HEADING = "### 自分への示唆"
SUMMARY_HEADING = "### 今日のサマリー（1文）"
STORIES_HEADING = "### なぜ動いたか（ストーリー）"
GEOPOLITICS_HEADING = "### 地政学と株式の因果関係"
FX_HEADING = "### 為替"
REFERENCES_HEADING = "### 参考記事"
_GEOPOLITICS_TABLE_HEAD = "| 地政学リスク | 今日の影響 | 関連銘柄・セクター |\n|---|---|---|"
# Cited sources that the model put in no reference group.
_UNGROUPED_CATEGORY = "その他"
_RULE = "\n\n---\n\n"
SECTORS_SECTION_HEADING = "### 今日のセクター動向（全セクター）"

# Markers that keep a non-confirmed claim from reading as fact.
_CONFIDENCE_MARKERS = {"confirmed": "", "inferred": "〔推測〕", "unknown": "〔未確認〕"}

# Bullet for a configured holding the LLM returned nothing for.
_MISSING_NOTE = "〔未確認〕今日の材料は確認できませんでした。"
# Bullet for every holding when the BriefScript call failed outright.
_FAILED_NOTE = "〔未確認〕本日の示唆は生成できませんでした。"
# Bullet for a sector with no claims: the model found no material move.
_QUIET_SECTOR_NOTE = "動き限定的"
# Bullet for a configured sector the LLM returned nothing for.
_MISSING_SECTOR_NOTE = "〔未確認〕今日の動きは確認できませんでした。"

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


def _number_sources(claims, first: int = 1) -> dict[str, int]:
    """Number source ids from ``first``, in order of first citation."""
    numbers: dict[str, int] = {}
    for claim in claims:
        for sid in claim.source_ids:
            numbers.setdefault(sid, len(numbers) + first)
    return numbers


def _source_list(numbers: dict[str, int], sources: list[Source]) -> list[str]:
    if not numbers:
        return []
    by_id = {source.id: source for source in sources}
    listed = [
        f"- ［{n}］[{_link_text(by_id[sid].title)}]({by_id[sid].url})"
        for sid, n in sorted(numbers.items(), key=lambda kv: kv[1])
    ]
    return ["\n".join([_SOURCES_HEADING, *listed])]


def render_holdings_markdown(
    section: HoldingsSection,
    quotes: dict[str, StockQuote],
    tickers: list[str],
    fx_change_pct: float | None = None,
    missing_note: str = _MISSING_NOTE,
    first_number: int = 1,
) -> str:
    """Render one ``####`` block per configured ticker, in configured order.

    Cited sources are numbered from ``first_number`` in order of first
    citation, marked ［n］ on the claims that cite them, and listed after the
    last holding.
    """
    notes = {note.ticker: note for note in section.holdings}
    tickers = _unique(tickers)
    numbers = _number_sources(
        (c for t in tickers if t in notes for c in notes[t].claims), first_number,
    )

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
    return "\n\n".join(blocks + _source_list(numbers, section.sources))


def render_sectors_markdown(section: SectorsSection, sectors: list[str]) -> str:
    """The sector sweep: every configured sector once, in configured order.

    Sector names are the configured spelling, so nothing the model writes
    becomes a heading.
    """
    notes = {note.sector: note for note in section.sectors}
    sectors = list(dict.fromkeys(" ".join(s.split()) for s in sectors if s.strip()))
    numbers = _number_sources(c for s in sectors if s in notes for c in notes[s].claims)

    blocks = [SECTORS_SECTION_HEADING]
    for sector in sectors:
        note = notes.get(sector)
        if note is None:
            bullets = [f"- {_MISSING_SECTOR_NOTE}"]
        elif not note.claims:
            bullets = [f"- {_QUIET_SECTOR_NOTE}"]
        else:
            bullets = [_bullet(c, numbers) for c in note.claims]
        tickers = [t for t in (_plain(x) for x in (note.related_tickers if note else ())) if t]
        if tickers:
            bullets.append(f"- 関連銘柄：{', '.join(tickers)}")
        blocks.append("\n".join([f"#### {_plain(sector)}", *bullets]))
    return "\n\n".join(blocks + _source_list(numbers, section.sources))


def _cell(text: str) -> str:
    # A pipe would split the table cell.
    return _plain(text).replace("|", "｜")


def _render_references(section: MainSection, numbers: dict[str, int]) -> str:
    by_id = {source.id: source for source in section.sources}
    groups = [(g.category, g.source_ids) for g in section.references]
    grouped = {sid for _, ids in groups for sid in ids}
    ungrouped = [sid for sid in numbers if sid not in grouped]
    if ungrouped:
        groups.append((_UNGROUPED_CATEGORY, ungrouped))
    blocks = [REFERENCES_HEADING]
    for category, ids in groups:
        listed = [
            f"- ［{numbers[sid]}］[{_link_text(by_id[sid].title)}]({by_id[sid].url})"
            for sid in sorted(ids, key=numbers.__getitem__)
        ]
        blocks.append("\n".join([f"#### {_plain(category)}", *listed]))
    return "\n\n".join(blocks)


def render_main_markdown(block: MainBlock, market: MarketSnapshot) -> str:
    """The main analysis in the layout the Markdown prompt used to produce.

    The FX lines are the fetcher's block verbatim: the model only adds
    commentary, so the rate shown is always the fetched one.
    """
    section = block.content
    numbers = _number_sources(section.claims())
    stories = [
        "\n".join([f"#### {_plain(story.title)}", *(_bullet(c, numbers) for c in story.claims)])
        for story in section.stories
    ]
    parts = [
        f"{SUMMARY_HEADING}\n\n{_plain(section.summary)}",
        "\n\n".join([STORIES_HEADING, *stories]),
    ]
    if section.geopolitics:
        rows = [
            f"| {_cell(row.risk)} | {_bullet(row.impact, numbers)[2:].replace('|', '｜')} "
            f"| {_cell(', '.join(row.related))} |"
            for row in section.geopolitics
        ]
        parts.append(f"{GEOPOLITICS_HEADING}\n\n{_GEOPOLITICS_TABLE_HEAD}\n" + "\n".join(rows))
    # A blank line keeps the commentary from reading as part of the fetcher's list.
    fx_blocks = [market.fx_context.strip()] if market.fx_context.strip() else []
    if section.fx.claims:
        fx_blocks.append("\n".join(_bullet(c, numbers) for c in section.fx.claims))
    if fx_blocks:
        parts.append(f"{FX_HEADING}\n\n" + "\n\n".join(fx_blocks))
    if block.holdings is not None:
        # Numbered after the main sources, so one ［n］ means one article here.
        holdings = _render_holdings_block(block.holdings, market, first_number=len(numbers) + 1)
        parts.append(f"{HOLDINGS_HEADING}\n\n{holdings}")
    if numbers:
        parts.append(_render_references(section, numbers))
    return _RULE.join(parts)


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
    """Freeze fetcher quotes into the document, so it re-renders offline.

    Only the snapshot's own fields are copied: the document is built after
    every claude call has been paid for, so a field added to ``StockQuote``
    must not turn into a ValidationError that loses the whole run.
    """
    fields = QuoteSnapshot.model_fields
    return MarketSnapshot(
        quotes=[
            QuoteSnapshot(**{k: v for k, v in dataclasses.asdict(q).items() if k in fields})
            for q in (quotes or {}).values()
        ],
        fx_change_pct=fx_change_pct,
    )


def _render_holdings_block(block: HoldingsBlock, market: MarketSnapshot, first_number: int = 1) -> str:
    quotes = {q.ticker: StockQuote(**q.model_dump()) for q in market.quotes}
    if block.content is None:
        return render_holdings_fallback(quotes, block.tickers, market.fx_change_pct)
    return render_holdings_markdown(
        block.content, quotes, block.tickers, market.fx_change_pct, first_number=first_number,
    )


def render_document_markdown(doc: BriefingDocument) -> str:
    """The briefing Markdown that Discord, Notion and the local file receive."""
    parts = []
    for section in doc.sections:
        if isinstance(section, HoldingsBlock):
            parts.append(_render_holdings_block(section, doc.market))
        elif isinstance(section, MainBlock):
            parts.append(render_main_markdown(section, doc.market))
        elif isinstance(section, SectorsBlock):
            parts.append(render_sectors_markdown(section.content, section.sectors))
        else:
            parts.append(section.text)
    return "".join(parts)
