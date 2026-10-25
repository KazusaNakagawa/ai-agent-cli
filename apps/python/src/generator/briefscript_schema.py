"""Pydantic models for BriefScript, the IR between the LLM and briefing renderers.

``BriefingDocument`` is the whole briefing: the fetcher's market snapshot plus
an ordered list of sections. The main analysis (#515), holdings ("自分への
示唆") and sector sweep (#514) are structured; failure notices and the
no-quotes Markdown briefing travel as ``MarkdownSection`` passthroughs. The
LLM writes claims; it never writes prices, FX rates or change figures — those
are not claim fields and are injected from the snapshot at render time.

Shape is enforced by the claude CLI's ``--json-schema`` (#504). The
cross-field rules below run on every validation; ticker membership needs the
configured holdings, which ``parse_holdings_section`` passes as validation
context. Without that context the membership check is skipped, so a cached or
nested section can be re-validated on its own.
"""
from __future__ import annotations

import copy
import datetime as dt
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationInfo,
    field_validator,
    model_validator,
)

Confidence = Literal["confirmed", "inferred", "unknown"]

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Source(BaseModel):
    model_config = _STRICT

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl


class Claim(BaseModel):
    model_config = _STRICT

    text: str = Field(min_length=1)
    confidence: Confidence
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        # A repeated id is harmless; dropping it is cheaper than a retry call.
        return list(dict.fromkeys(sid.strip() for sid in v))

    @model_validator(mode="after")
    def _confirmed_needs_source(self) -> Claim:
        if self.confidence == "confirmed" and not self.source_ids:
            raise ValueError("a confirmed claim must cite at least one source id")
        return self


class HoldingNote(BaseModel):
    model_config = _STRICT

    ticker: str = Field(min_length=1)
    # Matches the prompt's 1-3 claims; also emitted as maxItems for --json-schema.
    claims: list[Claim] = Field(min_length=1, max_length=3)
    next_event: str | None = None


class HoldingsSection(BaseModel):
    model_config = _STRICT

    holdings: list[HoldingNote]
    sources: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self, info: ValidationInfo) -> HoldingsSection:
        self.sources = _check_notes(
            self.holdings, "ticker", "ticker", self.sources,
            _canonical_names((info.context or {}).get("holdings"), "holdings", upper=True),
        )
        return self


class SectorNote(BaseModel):
    model_config = _STRICT

    sector: str = Field(min_length=1)
    # Empty means no material move today; the renderer says so.
    claims: list[Claim] = Field(default_factory=list, max_length=3)
    related_tickers: list[str] = Field(default_factory=list, max_length=5)


class SectorsSection(BaseModel):
    model_config = _STRICT

    sectors: list[SectorNote]
    sources: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self, info: ValidationInfo) -> SectorsSection:
        self.sources = _check_notes(
            self.sectors, "sector", "sector", self.sources,
            _canonical_names((info.context or {}).get("sectors"), "sectors", upper=False),
        )
        return self


def _check_notes(
    notes: list[Any],
    field: str,
    noun: str,
    sources: list[Source],
    canonical: dict[str, str] | None,
) -> list[Source]:
    """Shared cross-field checks; returns the sources that are actually cited.

    Every problem is collected and raised once, so a retry prompt can fix
    them all in a single extra claude CLI call. With ``canonical`` (the
    configured names), each note's name is matched and rewritten to the
    configured spelling.
    """
    errors: list[str] = []
    source_ids = _index_sources(sources, errors)

    seen: set[str] = set()
    cited: set[str] = set()
    for note in notes:
        name = getattr(note, field)
        if canonical is not None:
            configured = canonical.get(_fold(name, upper=noun == "ticker"))
            if configured is None:
                kind = "configured holding" if noun == "ticker" else "configured watch sector"
                errors.append(f"{noun} is not a {kind}: {name}")
            else:
                name = configured
                setattr(note, field, configured)
        if name in seen:
            errors.append(f"duplicate {noun}: {name}")
        seen.add(name)
        _check_citations(name, note.claims, source_ids, cited, errors)

    if errors:
        raise ValueError("; ".join(errors))
    # Uncited sources would only clutter the rendered source list.
    return [s for s in sources if s.id in cited]


def _index_sources(sources: list[Source], errors: list[str]) -> set[str]:
    source_ids: set[str] = set()
    for source in sources:
        if source.id in source_ids:
            errors.append(f"duplicate source id: {source.id}")
        source_ids.add(source.id)
    return source_ids


def _check_citations(
    where: str, claims: list[Claim], source_ids: set[str], cited: set[str], errors: list[str],
) -> None:
    for claim in claims:
        cited.update(claim.source_ids)
        unknown = [sid for sid in claim.source_ids if sid not in source_ids]
        if unknown:
            errors.append(f"{where}: claim cites unknown source id(s): {', '.join(unknown)}")


class Story(BaseModel):
    """One "why it moved" topic; the title is the model's, the claims carry the story."""

    model_config = _STRICT

    title: str = Field(min_length=1)
    claims: list[Claim] = Field(min_length=1, max_length=4)


class GeoImpact(BaseModel):
    """One row of the geopolitics table: a configured conflict and its market impact."""

    model_config = _STRICT

    risk: str = Field(min_length=1)
    impact: Claim
    # Tickers or sector names; free text, rendered flattened.
    related: list[str] = Field(default_factory=list, max_length=6)


class FxNote(BaseModel):
    """FX commentary only: the rate and its move are the fetcher's, not fields here."""

    model_config = _STRICT

    claims: list[Claim] = Field(default_factory=list, max_length=3)


class ReferenceGroup(BaseModel):
    model_config = _STRICT

    category: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class MainSection(BaseModel):
    """The main analysis (#515): summary, stories, geopolitics, FX and references."""

    model_config = _STRICT

    summary: str = Field(min_length=1)
    stories: list[Story] = Field(min_length=1, max_length=4)
    # At most one row per configured conflict; the schema pins and bounds it.
    geopolitics: list[GeoImpact] = Field(default_factory=list)
    fx: FxNote = Field(default_factory=FxNote)
    references: list[ReferenceGroup] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)

    def claims(self) -> list[Claim]:
        """Every claim, in rendering order (which is also citation-number order)."""
        return [
            *(c for story in self.stories for c in story.claims),
            *(row.impact for row in self.geopolitics),
            *self.fx.claims,
        ]

    @model_validator(mode="after")
    def _check_references(self, info: ValidationInfo) -> MainSection:
        errors: list[str] = []
        source_ids = _index_sources(self.sources, errors)
        cited: set[str] = set()
        for story in self.stories:
            _check_citations(f"story {story.title}", story.claims, source_ids, cited, errors)
        canonical = _canonical_names((info.context or {}).get("conflicts"), "conflicts", upper=False)
        seen: set[str] = set()
        for row in self.geopolitics:
            if canonical is not None:
                configured = canonical.get(_fold(row.risk, upper=False))
                if configured is None:
                    errors.append(f"risk is not a configured geopolitical conflict: {row.risk}")
                else:
                    row.risk = configured
            if row.risk in seen:
                errors.append(f"duplicate risk: {row.risk}")
            seen.add(row.risk)
            _check_citations(f"geopolitics {row.risk}", [row.impact], source_ids, cited, errors)
        _check_citations("fx", self.fx.claims, source_ids, cited, errors)
        for group in self.references:
            unknown = [sid for sid in group.source_ids if sid not in source_ids]
            if unknown:
                errors.append(
                    f"reference group {group.category} lists unknown source id(s): {', '.join(unknown)}"
                )
        if errors:
            raise ValueError("; ".join(errors))
        # References list only what a claim cites, each source in its first group.
        self.sources = [s for s in self.sources if s.id in cited]
        grouped: set[str] = set()
        groups = []
        for group in self.references:
            ids = [sid for sid in dict.fromkeys(group.source_ids) if sid in cited and sid not in grouped]
            grouped.update(ids)
            if ids:
                groups.append(group.model_copy(update={"source_ids": ids}))
        self.references = groups
        return self


# Envelope models carry text verbatim: stripping a passthrough section would
# change the rendered Markdown.
_ENVELOPE = ConfigDict(extra="forbid")


class QuoteSnapshot(BaseModel):
    """A fetcher quote as stored in the document, mirroring ``StockQuote``."""

    model_config = _ENVELOPE

    ticker: str
    last_price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None
    currency: str = "USD"
    error: str | None = None


class MarketSnapshot(BaseModel):
    """The figures a renderer may print; nothing else may supply them."""

    model_config = _ENVELOPE

    quotes: list[QuoteSnapshot] = Field(default_factory=list)
    fx_change_pct: float | None = None
    # The fetcher's FX block (rates, range, 200-day line, scenarios) as text.
    fx_context: str = ""


class MarkdownSection(BaseModel):
    """Text not yet migrated to a structured section, rendered as-is."""

    model_config = _ENVELOPE

    kind: Literal["markdown"] = "markdown"
    text: str


class HoldingsBlock(BaseModel):
    """The holdings section body; ``content`` is None when its call failed."""

    model_config = _ENVELOPE

    kind: Literal["holdings"] = "holdings"
    tickers: list[str]
    content: HoldingsSection | None = None


class SectorsBlock(BaseModel):
    """The sector sweep body, listing every configured watch sector."""

    model_config = _ENVELOPE

    kind: Literal["sectors"] = "sectors"
    sectors: list[str]
    content: SectorsSection


class MainBlock(BaseModel):
    """The main analysis, with the holdings section laid out inside it."""

    model_config = _ENVELOPE

    kind: Literal["main"] = "main"
    content: MainSection
    holdings: HoldingsBlock | None = None


Section = Annotated[
    Union[MarkdownSection, HoldingsBlock, SectorsBlock, MainBlock], Field(discriminator="kind"),
]


class BriefingDocument(BaseModel):
    model_config = _ENVELOPE

    version: Literal[1] = 1
    date: dt.date
    market: MarketSnapshot = Field(default_factory=MarketSnapshot)
    sections: list[Section] = Field(default_factory=list)


def _fold(name: str, *, upper: bool) -> str:
    # Tickers compare case-insensitively; sector names (often Japanese) only
    # ignore surrounding and repeated whitespace.
    name = " ".join(name.split())
    return name.upper() if upper else name


def _canonical_names(names: Any, what: str, *, upper: bool) -> dict[str, str] | None:
    """Map folded name → configured spelling, or None when not given."""
    if names is None:
        return None
    if isinstance(names, str):
        raise TypeError(f"{what} must be a list of names, not a str")
    return {_fold(n, upper=upper): " ".join(n.split()) for n in names}


def parse_holdings_section(data: Any, holdings: list[str]) -> HoldingsSection:
    """Validate an LLM payload against the configured ``holdings`` tickers.

    Tickers are matched case-insensitively and rewritten to the configured
    spelling; anything else (e.g. a missing exchange suffix) is rejected.
    """
    _canonical_names(holdings, "holdings", upper=True)
    return HoldingsSection.model_validate(data, context={"holdings": holdings})


def parse_sectors_section(data: Any, sectors: list[str]) -> SectorsSection:
    """Validate an LLM payload against the configured watch ``sectors``."""
    _canonical_names(sectors, "sectors", upper=False)
    return SectorsSection.model_validate(data, context={"sectors": sectors})


def _pinned_schema(model: type[BaseModel], note: str, field: str, names: list[str]) -> dict[str, Any]:
    if isinstance(names, str):
        raise TypeError(f"{field} names must be a list, not a str")
    schema = copy.deepcopy(model.model_json_schema())
    schema["$defs"][note]["properties"][field]["enum"] = list(names)
    return schema


def holdings_json_schema(holdings: list[str]) -> dict[str, Any]:
    """JSON Schema for ``--json-schema`` with ``ticker`` pinned to ``holdings``."""
    return _pinned_schema(HoldingsSection, "HoldingNote", "ticker", holdings)


def sectors_json_schema(sectors: list[str]) -> dict[str, Any]:
    """JSON Schema for ``--json-schema`` with ``sector`` pinned to ``sectors``."""
    return _pinned_schema(SectorsSection, "SectorNote", "sector", sectors)


def parse_main_section(data: Any, conflicts: list[str]) -> MainSection:
    """Validate the main analysis against the configured geopolitical ``conflicts``."""
    _canonical_names(conflicts, "conflicts", upper=False)
    return MainSection.model_validate(data, context={"conflicts": conflicts})


def main_json_schema(conflicts: list[str]) -> dict[str, Any]:
    """JSON Schema for the main call: one geopolitics row per configured conflict at most."""
    if isinstance(conflicts, str):
        raise TypeError("conflicts must be a list, not a str")
    schema = copy.deepcopy(MainSection.model_json_schema())
    schema["properties"]["geopolitics"]["maxItems"] = len(conflicts)
    if conflicts:
        schema["$defs"]["GeoImpact"]["properties"]["risk"]["enum"] = list(conflicts)
    return schema
