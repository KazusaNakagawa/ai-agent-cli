"""Render a ``BriefingDocument`` as a script to be read aloud (#517).

The same sections as the Markdown briefing, written for the ear: no URLs,
source numbers or Markdown, confidence spoken as a phrase instead of a
〔推測〕 marker, and each holding's move read from the fetcher quotes in the
document's market snapshot. The source lists and references are left out —
they only make sense on a page.

The script is one paragraph per topic, one line per paragraph. ``max_chars``
trims it by whole sentences, so a shortened briefing never stops mid-sentence.
"""
from __future__ import annotations

import re

from src.fetcher.stocks import StockQuote, to_jpy_change_pct
from src.generator.briefscript_render import (
    _FAILED_NOTE,
    _MISSING_NOTE,
    REFERENCES_HEADING,
    _plain,
    _unique,
    _URL_PLACEHOLDER,
)
from src.generator.briefscript_schema import (
    BriefingDocument,
    Claim,
    HoldingsBlock,
    MainBlock,
    MarketSnapshot,
    SectorsBlock,
)

_CLOSING = "以上です。"
_SPOKEN_CONFIDENCE = {"confirmed": "", "inferred": "推測ですが、", "unknown": "未確認ですが、"}
_QUOTE_FAILED = "株価を取得できませんでした"
_QUIET_SECTOR = "目立った動きはありませんでした"

# Written-only marks: emphasis, code, heading hashes, ［n］ citations and the
# 〔推測〕 / 〔未確認〕 markers the page versions carry.
_MARKS = re.compile(r"[*`#]|［\d+］|〔[^〕]*〕")
_SENTENCE_END = ("。", "！", "？", "!", "?")
# Markdown passthrough lines that carry nothing to say: rules, table
# separators and the bold "出典" label above a source list.
_SILENT_LINE = re.compile(r"^(?:[-*_]{3,}|[\s|:-]+|\*\*出典\*\*)$")
_LIST_MARKER = re.compile(r"^(?:[-*+]|\d+[.)])\s+|^>\s*")
# A source-list item: an optional ［n］ and nothing but a link.
_SOURCE_ITEM = re.compile(r"^(?:［\d+］)?\s*\[[^\]]*\]\([^)]*\)$")


def _say(text: str) -> str:
    """One spoken sentence: inert, unmarked, and ending in 。 (or "" if empty)."""
    text = _plain(text).replace(_URL_PLACEHOLDER, "")
    text = _MARKS.sub("", text).replace("|", "、")
    text = " ".join(text.split())
    if text and not text.endswith(_SENTENCE_END):
        text += "。"
    return text


def _claim(claim: Claim) -> str:
    text = _say(claim.text)
    return f"{_SPOKEN_CONFIDENCE[claim.confidence]}{text}" if text else ""


def _move(pct: float) -> str:
    if round(abs(pct), 1) == 0:
        return "横ばい"
    return f"{abs(pct):.1f}%{'高' if pct > 0 else '安'}"


def _quote_line(ticker: str, quote: StockQuote | None, fx_change_pct: float | None) -> str:
    if quote is None or quote.error or quote.change_pct is None:
        return f"{ticker}は、{_QUOTE_FAILED}。"
    if quote.currency != "USD":
        return f"{ticker}は、{_move(quote.change_pct)}。"
    line = f"{ticker}は、ドル建てで{_move(quote.change_pct)}"
    if fx_change_pct is not None:
        line += f"、円建てで{_move(to_jpy_change_pct(quote.change_pct, fx_change_pct))}"
    return line + "。"


def _holdings(block: HoldingsBlock, market: MarketSnapshot) -> list[list[str]]:
    quotes = {q.ticker: StockQuote(**q.model_dump()) for q in market.quotes}
    notes = {note.ticker: note for note in block.content.holdings} if block.content else {}
    missing = _say(_MISSING_NOTE if block.content else _FAILED_NOTE)

    paragraphs = []
    for ticker in _unique(block.tickers):
        name = _say(ticker).rstrip("。")
        sentences = [_quote_line(name, quotes.get(ticker), market.fx_change_pct)]
        note = notes.get(ticker)
        if note is None:
            sentences.append(missing)
        else:
            sentences += [_claim(c) for c in note.claims]
            if note.next_event and _say(note.next_event):
                sentences.append(f"次の予定は、{_say(note.next_event)}")
        paragraphs.append(sentences)
    return paragraphs


def _sectors(block: SectorsBlock) -> list[list[str]]:
    notes = {note.sector: note for note in block.content.sectors}
    paragraphs = []
    for sector in dict.fromkeys(" ".join(s.split()) for s in block.sectors if s.strip()):
        note = notes.get(sector)
        # A sector the model returned nothing for has nothing to say aloud.
        if note is None:
            continue
        name = _say(sector)
        if not note.claims:
            paragraphs.append([f"{name.rstrip('。')}は、{_QUIET_SECTOR}。"])
        else:
            paragraphs.append([name, *(_claim(c) for c in note.claims)])
    return paragraphs


def _main(block: MainBlock, market: MarketSnapshot) -> list[list[str]]:
    section = block.content
    paragraphs = [[_say(section.summary)]]
    for story in section.stories:
        paragraphs.append([_say(story.title), *(_claim(c) for c in story.claims)])
    for row in section.geopolitics:
        paragraphs.append([f"{_say(row.risk).rstrip('。')}について。", _claim(row.impact)])
    if section.fx.claims:
        paragraphs.append(["為替。", *(_claim(c) for c in section.fx.claims)])
    if block.holdings is not None:
        paragraphs += _holdings(block.holdings, market)
    return paragraphs


def _markdown(text: str) -> list[list[str]]:
    """Speakable lines of a Markdown passthrough, without its source lists."""
    sentences = []
    in_references = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            in_references = line == REFERENCES_HEADING
        if in_references or not line or _SILENT_LINE.match(line):
            continue
        line = _LIST_MARKER.sub("", line)
        if _SOURCE_ITEM.match(line):
            continue
        sentences.append(_say(line))
    return [sentences]


def _fit(opening: str, paragraphs: list[list[str]], max_chars: int | None) -> str:
    """Join the script, dropping every sentence from the first that overflows."""
    # Each kept paragraph costs its sentences plus one newline.
    budget = float("inf") if max_chars is None else max_chars - len(opening) - 1 - len(_CLOSING)
    lines = [opening]
    for paragraph in paragraphs:
        kept = ""
        for sentence in paragraph:
            cost = len(sentence) + (0 if kept else 1)
            if cost > budget:
                if kept:
                    lines.append(kept)
                return "\n".join([*lines, _CLOSING])
            kept += sentence
            budget -= cost
        if kept:
            lines.append(kept)
    return "\n".join([*lines, _CLOSING])


def render_document_speech(doc: BriefingDocument, max_chars: int | None = None) -> str:
    """The briefing as a script for text-to-speech, at most ``max_chars`` long."""
    paragraphs: list[list[str]] = []
    for section in doc.sections:
        if isinstance(section, MainBlock):
            paragraphs += _main(section, doc.market)
        elif isinstance(section, HoldingsBlock):
            paragraphs += _holdings(section, doc.market)
        elif isinstance(section, SectorsBlock):
            paragraphs += _sectors(section)
        else:
            paragraphs += _markdown(section.text)
    paragraphs = [[s for s in p if s] for p in paragraphs]
    opening = f"{doc.date.month}月{doc.date.day}日のマーケットブリーフィングです。"
    return _fit(opening, paragraphs, max_chars)
