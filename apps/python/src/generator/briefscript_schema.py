"""Pydantic models for BriefScript, the IR between the LLM and briefing renderers.

Only the holdings ("自分への示唆") section is modelled so far. The LLM writes
claims; it never writes prices or change figures — those are not fields here
and are injected from fetcher data at render time.

Shape is enforced by the claude CLI's ``--json-schema`` (#504); the cross-field
rules below (source ids resolve, tickers are configured holdings) need the
configured holdings, passed as validation context via ``parse_holdings_section``.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

Confidence = Literal["confirmed", "inferred", "unknown"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(pattern=r"^https?://\S+$")


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    confidence: Confidence
    source_ids: list[str] = Field(default_factory=list)


class HoldingNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    claims: list[Claim] = Field(min_length=1)
    next_event: str | None = None


class HoldingsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holdings: list[HoldingNote]
    sources: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self, info: ValidationInfo) -> HoldingsSection:
        configured = (info.context or {}).get("holdings")
        if configured is None:
            raise ValueError("configured holdings must be passed as validation context")
        configured = set(configured)

        source_ids: set[str] = set()
        for source in self.sources:
            if source.id in source_ids:
                raise ValueError(f"duplicate source id: {source.id}")
            source_ids.add(source.id)

        seen: set[str] = set()
        for note in self.holdings:
            if note.ticker not in configured:
                raise ValueError(f"ticker is not a configured holding: {note.ticker}")
            if note.ticker in seen:
                raise ValueError(f"duplicate ticker: {note.ticker}")
            seen.add(note.ticker)
            for claim in note.claims:
                unknown = [sid for sid in claim.source_ids if sid not in source_ids]
                if unknown:
                    raise ValueError(
                        f"{note.ticker}: claim cites unknown source id(s): {', '.join(unknown)}"
                    )
        return self


def parse_holdings_section(data: Any, holdings: list[str]) -> HoldingsSection:
    """Validate an LLM payload against the configured ``holdings`` tickers."""
    return HoldingsSection.model_validate(data, context={"holdings": holdings})
