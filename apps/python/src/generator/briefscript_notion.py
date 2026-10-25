"""Render a ``BriefingDocument`` straight to Notion blocks (#516).

The page mirrors the Markdown briefing section for section, but structured
parts are built as native blocks instead of being re-parsed from text:
confidence is a coloured label, ［n］ markers link to their source, the
geopolitics rows are a table and the summary is a callout. ``MarkdownSection``
passthroughs (failure notices, the no-quotes briefing) still go through
``markdown_to_notion_blocks``.

Every rich-text item stays within Notion's 2000-character limit; the
100-block request limit is the notifier's job (``_create_page``).
"""
from __future__ import annotations

from src.constants import NOTION_CHAR_LIMIT
from src.fetcher.stocks import StockQuote
from src.generator.briefscript_render import (
    _CONFIDENCE_MARKERS,
    _FAILED_NOTE,
    _MISSING_NOTE,
    _MISSING_SECTOR_NOTE,
    _QUIET_SECTOR_NOTE,
    FX_HEADING,
    GEOPOLITICS_HEADING,
    HOLDINGS_HEADING,
    REFERENCES_HEADING,
    SECTORS_SECTION_HEADING,
    STORIES_HEADING,
    SUMMARY_HEADING,
    _heading,
    _number_sources,
    _plain,
    _unique,
    reference_groups,
)
from src.generator.briefscript_schema import (
    BriefingDocument,
    Claim,
    HoldingsBlock,
    MainBlock,
    MarketSnapshot,
    SectorsBlock,
    Source,
)
from src.notifier.markdown import markdown_to_notion_blocks

_CONFIDENCE_COLORS = {"inferred": "orange", "unknown": "gray"}
_SOURCES_LABEL = "出典"
_GEOPOLITICS_COLUMNS = ("地政学リスク", "今日の影響", "関連銘柄・セクター")


def _text(content: str, *, color: str | None = None, bold: bool = False, url: str | None = None) -> list[dict]:
    """Rich text for ``content``, split into items of at most 2000 characters."""
    items = []
    for i in range(0, max(len(content), 1), NOTION_CHAR_LIMIT):
        text: dict = {"content": content[i:i + NOTION_CHAR_LIMIT]}
        if url:
            text["link"] = {"url": url}
        item: dict = {"type": "text", "text": text}
        annotations = {k: v for k, v in (("color", color), ("bold", bold)) if v}
        if annotations:
            item["annotations"] = annotations
        items.append(item)
    return items


def _block(kind: str, rich_text: list[dict], **extra) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": rich_text, **extra}}


def _heading_block(text: str) -> dict:
    # The Markdown path maps both ### and #### to heading_3; keep the same page.
    return _block("heading_3", _text(text.lstrip("# ")))


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _bullet(rich_text: list[dict]) -> dict:
    return _block("bulleted_list_item", rich_text)


def _claim_text(claim: Claim, numbers: dict[str, int], urls: dict[str, str]) -> list[dict]:
    marker = _CONFIDENCE_MARKERS[claim.confidence]
    rich = _text(marker, color=_CONFIDENCE_COLORS[claim.confidence]) if marker else []
    rich += _text(_plain(claim.text))
    for sid in claim.source_ids:
        rich += _text(f"［{numbers[sid]}］", url=urls.get(sid))
    return rich


def _claim_bullets(claims, numbers: dict[str, int], sources: list[Source]) -> list[dict]:
    urls = {source.id: str(source.url) for source in sources}
    return [_bullet(_claim_text(c, numbers, urls)) for c in claims]


def _source_items(sources: list[Source], numbers: dict[str, int]) -> list[dict]:
    # Bullets carrying ［n］, not numbered_list_item: holdings inside the main
    # block are numbered after the main sources, which Notion's own counter
    # cannot start from.
    return [
        _bullet(_text(f"［{numbers[s.id]}］") + _text(_plain(s.title), url=str(s.url)))
        for s in sorted((s for s in sources if s.id in numbers), key=lambda s: numbers[s.id])
    ]


def _source_list(sources: list[Source], numbers: dict[str, int]) -> list[dict]:
    items = _source_items(sources, numbers)
    return [_block("paragraph", _text(_SOURCES_LABEL, bold=True)), *items] if items else []


def _quotes(market: MarketSnapshot) -> dict[str, StockQuote]:
    return {q.ticker: StockQuote(**q.model_dump()) for q in market.quotes}


def _holdings_blocks(block: HoldingsBlock, market: MarketSnapshot, first_number: int = 1) -> list[dict]:
    quotes = _quotes(market)
    content = block.content
    notes = {note.ticker: note for note in content.holdings} if content else {}
    tickers = _unique(block.tickers)
    numbers = _number_sources(
        (c for t in tickers if t in notes for c in notes[t].claims), first_number,
    )
    sources = content.sources if content else []
    missing = _MISSING_NOTE if content else _FAILED_NOTE

    blocks = []
    for ticker in tickers:
        blocks.append(_heading_block(_heading(ticker, quotes.get(ticker), market.fx_change_pct)))
        note = notes.get(ticker)
        if note is None:
            blocks.append(_bullet(_text(missing)))
            continue
        blocks += _claim_bullets(note.claims, numbers, sources)
        if note.next_event:
            blocks.append(_bullet(_text(f"次の予定：{_plain(note.next_event)}")))
    return blocks + _source_list(sources, numbers)


def _sectors_blocks(block: SectorsBlock) -> list[dict]:
    section = block.content
    notes = {note.sector: note for note in section.sectors}
    sectors = list(dict.fromkeys(" ".join(s.split()) for s in block.sectors if s.strip()))
    numbers = _number_sources(c for s in sectors if s in notes for c in notes[s].claims)

    blocks = [_heading_block(SECTORS_SECTION_HEADING)]
    for sector in sectors:
        blocks.append(_heading_block(_plain(sector)))
        note = notes.get(sector)
        if note is None:
            blocks.append(_bullet(_text(_MISSING_SECTOR_NOTE)))
        elif not note.claims:
            blocks.append(_bullet(_text(_QUIET_SECTOR_NOTE)))
        else:
            blocks += _claim_bullets(note.claims, numbers, section.sources)
        tickers = [t for t in (_plain(x) for x in (note.related_tickers if note else ())) if t]
        if tickers:
            blocks.append(_bullet(_text(f"関連銘柄：{', '.join(tickers)}")))
    return blocks + _source_list(section.sources, numbers)


def _table(rows: list[list[list[dict]]]) -> dict:
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(_GEOPOLITICS_COLUMNS),
            "has_column_header": True,
            "has_row_header": False,
            "children": [{"type": "table_row", "table_row": {"cells": cells}} for cells in rows],
        },
    }


def _main_blocks(block: MainBlock, market: MarketSnapshot) -> list[dict]:
    section = block.content
    numbers = _number_sources(section.claims())
    urls = {source.id: str(source.url) for source in section.sources}

    parts: list[list[dict]] = [
        [_heading_block(SUMMARY_HEADING), _block("callout", _text(_plain(section.summary)))],
        [_heading_block(STORIES_HEADING)] + [
            b for story in section.stories
            for b in [_heading_block(_plain(story.title)),
                      *_claim_bullets(story.claims, numbers, section.sources)]
        ],
    ]
    if section.geopolitics:
        header = [_text(column, bold=True) for column in _GEOPOLITICS_COLUMNS]
        rows = [
            [_text(_plain(row.risk)), _claim_text(row.impact, numbers, urls),
             _text(_plain(", ".join(row.related)))]
            for row in section.geopolitics
        ]
        parts.append([_heading_block(GEOPOLITICS_HEADING), _table([header, *rows])])
    # The fetcher's block is plain Markdown text; its figures pass through untouched.
    fx = markdown_to_notion_blocks(market.fx_context) if market.fx_context.strip() else []
    fx += _claim_bullets(section.fx.claims, numbers, section.sources)
    if fx:
        parts.append([_heading_block(FX_HEADING), *fx])
    if block.holdings is not None:
        parts.append([
            _heading_block(HOLDINGS_HEADING),
            *_holdings_blocks(block.holdings, market, first_number=len(numbers) + 1),
        ])
    if numbers:
        refs = [_heading_block(REFERENCES_HEADING)]
        for category, sources in reference_groups(section, numbers):
            refs += [_heading_block(_plain(category)), *_source_items(sources, numbers)]
        parts.append(refs)

    blocks: list[dict] = []
    for i, part in enumerate(parts):
        blocks += ([_divider()] if i else []) + part
    return blocks


def render_document_notion(doc: BriefingDocument) -> list[dict]:
    """The briefing as Notion blocks, in the Markdown version's order."""
    blocks: list[dict] = []
    for section in doc.sections:
        if isinstance(section, MainBlock):
            blocks += _main_blocks(section, doc.market)
        elif isinstance(section, HoldingsBlock):
            blocks += _holdings_blocks(section, doc.market)
        elif isinstance(section, SectorsBlock):
            blocks += _sectors_blocks(section)
        else:
            blocks += markdown_to_notion_blocks(section.text)
    return blocks
