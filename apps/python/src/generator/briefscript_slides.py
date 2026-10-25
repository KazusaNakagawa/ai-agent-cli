"""Render a ``BriefingDocument`` as a Marp slide deck for weekly review (#518).

One slide per part of the briefing: the summary, each story, geopolitics, FX,
each holding and the sector sweep, then the cited sources on the last
slide(s). No slide carries more than ``max_claims`` claims — a story is cut
there, while geopolitics and sectors continue on another slide, since each
row there is a different topic. Sources are numbered once for the whole
deck, and only the ones a shown claim cites are listed.

``MarkdownSection`` passthroughs (failure notices, the no-quotes briefing)
are left out: a deck is made from the structured parts only.

Converting to PDF / PPTX is the Marp CLI's job and is not run here, e.g.
``npx @marp-team/marp-cli briefing_2026-10-25.slides.md --pdf``.
"""
from __future__ import annotations

from src.fetcher.stocks import StockQuote
from src.generator.briefscript_render import (
    _CONFIDENCE_MARKERS,
    _FAILED_NOTE,
    _MISSING_NOTE,
    _QUIET_SECTOR_NOTE,
    FX_HEADING,
    GEOPOLITICS_HEADING,
    _heading,
    _link_text,
    _plain,
    _unique,
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

DEFAULT_MAX_CLAIMS = 3
_FRONT_MATTER = "---\nmarp: true\npaginate: true\n---"
_SLIDE_BREAK = "\n\n---\n\n"
_TITLE = "マーケットブリーフィング"
_SUMMARY_TITLE = "今日のサマリー"
_SECTORS_TITLE = "セクター動向"
_SOURCES_TITLE = "出典"
_SOURCES_PER_SLIDE = 10


def _text(text: str) -> str:
    """Model text, inert in Marp too: one line, and no raw HTML."""
    return _plain(text).replace("<", "＜").replace(">", "＞")


def _title(text: str) -> str:
    # The page headings are ### / ####; a slide title is ##.
    return "## " + text.lstrip("# ")


def _chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


class _Deck:
    """Slides plus the deck-wide source numbering."""

    def __init__(self, max_claims: int):
        self.max_claims = max_claims
        self.slides: list[str] = []
        # Keyed by URL: ids are only unique within one section, and the same
        # article cited from two sections is one source.
        self.numbers: dict[str, int] = {}
        self.titles: dict[str, str] = {}

    def add(self, title: str, lines: list[str]) -> None:
        self.slides.append("\n".join([_title(title), "", *lines]) if lines else _title(title))

    def claim(self, claim: Claim, sources: list[Source]) -> str:
        by_id = {source.id: source for source in sources}
        refs = ""
        for sid in claim.source_ids:
            source = by_id[sid]
            url = str(source.url)
            number = self.numbers.setdefault(url, len(self.numbers) + 1)
            self.titles.setdefault(url, source.title)
            refs += f"［{number}］"
        return f"{_CONFIDENCE_MARKERS[claim.confidence]}{_text(claim.text)}{refs}"

    def claims(self, claims, sources: list[Source]) -> list[str]:
        return [f"- {self.claim(c, sources)}" for c in claims[: self.max_claims]]

    def sources(self) -> None:
        listed = [
            f"- ［{n}］[{_link_text(self.titles[url]).replace('<', '＜').replace('>', '＞')}]({url})"
            for url, n in sorted(self.numbers.items(), key=lambda kv: kv[1])
        ]
        for chunk in _chunks(listed, _SOURCES_PER_SLIDE):
            self.add(_SOURCES_TITLE, chunk)


def _holdings(deck: _Deck, block: HoldingsBlock, market: MarketSnapshot) -> None:
    quotes = {q.ticker: StockQuote(**q.model_dump()) for q in market.quotes}
    content = block.content
    notes = {note.ticker: note for note in content.holdings} if content else {}
    sources = content.sources if content else []
    missing = _MISSING_NOTE if content else _FAILED_NOTE
    for ticker in _unique(block.tickers):
        note = notes.get(ticker)
        if note is None:
            lines = [f"- {missing}"]
        else:
            lines = deck.claims(note.claims, sources)
            if note.next_event:
                lines.append(f"- 次の予定：{_text(note.next_event)}")
        deck.add(_heading(ticker, quotes.get(ticker), market.fx_change_pct), lines)


def _sectors(deck: _Deck, block: SectorsBlock) -> None:
    notes = {note.sector: note for note in block.content.sectors}
    moved, quiet = [], []
    for sector in dict.fromkeys(" ".join(s.split()) for s in block.sectors if s.strip()):
        note = notes.get(sector)
        if note is None:
            continue
        if note.claims:
            # One claim per sector: the deck is an overview, the page has the rest.
            moved.append(f"- {_text(sector)}：{deck.claim(note.claims[0], block.content.sources)}")
        else:
            quiet.append(_text(sector))
    slides = _chunks(moved, deck.max_claims) or ([[]] if quiet else [])
    if quiet:
        slides[-1] = [*slides[-1], f"- {_QUIET_SECTOR_NOTE}：{', '.join(quiet)}"]
    for lines in slides:
        deck.add(_SECTORS_TITLE, lines)


def _fx_lines(fx_context: str) -> list[str]:
    # The fetcher's own lines, as paragraphs: they are figures, not claims.
    lines = [line.strip().removeprefix("- ") for line in fx_context.splitlines()
             if line.strip() and not line.startswith((" ", "\t"))]
    return [line for pair in zip(lines, [""] * len(lines)) for line in pair][:-1]


def _main(deck: _Deck, block: MainBlock, market: MarketSnapshot) -> None:
    section = block.content
    deck.add(_SUMMARY_TITLE, [_text(section.summary)])
    for story in section.stories:
        deck.add(_text(story.title), deck.claims(story.claims, section.sources))
    rows = [
        f"- {_text(row.risk)}：{deck.claim(row.impact, section.sources)}"
        for row in section.geopolitics
    ]
    for chunk in _chunks(rows, deck.max_claims):
        deck.add(GEOPOLITICS_HEADING, chunk)
    fx = _fx_lines(market.fx_context)
    claims = deck.claims(section.fx.claims, section.sources)
    if fx or claims:
        deck.add(FX_HEADING, fx + ([""] if fx and claims else []) + claims)
    if block.holdings is not None:
        _holdings(deck, block.holdings, market)


def render_document_slides(doc: BriefingDocument, max_claims: int = DEFAULT_MAX_CLAIMS) -> str:
    """The briefing as Marp Markdown, at most ``max_claims`` claims per slide."""
    if max_claims < 1:
        raise ValueError(f"max_claims must be >= 1 (got {max_claims})")
    deck = _Deck(max_claims)
    deck.slides.append(f"# {_TITLE}\n\n{doc.date.isoformat()}")
    for section in doc.sections:
        if isinstance(section, MainBlock):
            _main(deck, section, doc.market)
        elif isinstance(section, HoldingsBlock):
            _holdings(deck, section, doc.market)
        elif isinstance(section, SectorsBlock):
            _sectors(deck, section)
    deck.sources()
    return _FRONT_MATTER + "\n\n" + _SLIDE_BREAK.join(deck.slides) + "\n"
