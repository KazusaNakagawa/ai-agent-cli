"""Pydantic models for BriefScript, the IR between the LLM and briefing renderers.

Only the holdings ("自分への示唆") section is modelled so far. The LLM writes
claims; it never writes prices or change figures — those are not fields here
and are injected from fetcher data at render time.

Shape is enforced by the claude CLI's ``--json-schema`` (#504). The
cross-field rules below run on every validation; ticker membership needs the
configured holdings, which ``parse_holdings_section`` passes as validation
context. Without that context the membership check is skipped, so a cached or
nested section can be re-validated on its own.
"""
from __future__ import annotations

import copy
from typing import Any, Literal

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
        # Collect every problem and raise once, so a retry prompt can fix
        # them all in a single extra claude CLI call.
        errors: list[str] = []
        canonical = _canonical_tickers((info.context or {}).get("holdings"))

        source_ids: set[str] = set()
        for source in self.sources:
            if source.id in source_ids:
                errors.append(f"duplicate source id: {source.id}")
            source_ids.add(source.id)

        seen: set[str] = set()
        cited: set[str] = set()
        for note in self.holdings:
            if canonical is not None:
                configured = canonical.get(note.ticker.upper())
                if configured is None:
                    errors.append(f"ticker is not a configured holding: {note.ticker}")
                else:
                    note.ticker = configured
            if note.ticker in seen:
                errors.append(f"duplicate ticker: {note.ticker}")
            seen.add(note.ticker)
            for claim in note.claims:
                cited.update(claim.source_ids)
                unknown = [sid for sid in claim.source_ids if sid not in source_ids]
                if unknown:
                    errors.append(
                        f"{note.ticker}: claim cites unknown source id(s): {', '.join(unknown)}"
                    )

        if errors:
            raise ValueError("; ".join(errors))
        # Uncited sources would only clutter the rendered source list.
        self.sources = [s for s in self.sources if s.id in cited]
        return self


def _canonical_tickers(holdings: Any) -> dict[str, str] | None:
    """Map upper-cased ticker → configured spelling, or None when not given."""
    if holdings is None:
        return None
    if isinstance(holdings, str):
        raise TypeError("holdings must be a list of tickers, not a str")
    return {t.strip().upper(): t.strip() for t in holdings}


def parse_holdings_section(data: Any, holdings: list[str]) -> HoldingsSection:
    """Validate an LLM payload against the configured ``holdings`` tickers.

    Tickers are matched case-insensitively and rewritten to the configured
    spelling; anything else (e.g. a missing exchange suffix) is rejected.
    """
    _canonical_tickers(holdings)
    return HoldingsSection.model_validate(data, context={"holdings": holdings})


def holdings_json_schema(holdings: list[str]) -> dict[str, Any]:
    """JSON Schema for ``--json-schema`` with ``ticker`` pinned to ``holdings``."""
    if isinstance(holdings, str):
        raise TypeError("holdings must be a list of tickers, not a str")
    schema = copy.deepcopy(HoldingsSection.model_json_schema())
    schema["$defs"]["HoldingNote"]["properties"]["ticker"]["enum"] = list(holdings)
    return schema
