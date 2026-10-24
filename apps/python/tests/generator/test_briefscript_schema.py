import json
import pathlib

import pytest
from pydantic import ValidationError

from src.generator.briefscript_schema import (
    Claim,
    HoldingNote,
    HoldingsSection,
    Source,
    parse_holdings_section,
)

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "briefscript"
HOLDINGS = ["TICKER1", "TICKER2"]


def _payload(**overrides) -> dict:
    data = {
        "holdings": [
            {
                "ticker": "TICKER1",
                "claims": [
                    {"text": "決算は予想を上回った。", "confidence": "confirmed", "source_ids": ["s1"]},
                    {"text": "円建ての下落は為替による。", "confidence": "inferred", "source_ids": []},
                ],
                "next_event": "10/28 決算",
            },
            {
                "ticker": "TICKER2",
                "claims": [
                    {"text": "今日の下落理由は特定できませんでした。", "confidence": "unknown", "source_ids": []},
                ],
            },
        ],
        "sources": [
            {"id": "s1", "title": "Q3 earnings release", "url": "https://example.com/q3"},
        ],
    }
    data.update(overrides)
    return data


# --- success ---

def test_valid_payload_parses():
    section = parse_holdings_section(_payload(), holdings=HOLDINGS)
    assert [h.ticker for h in section.holdings] == ["TICKER1", "TICKER2"]
    assert section.holdings[0].claims[1].confidence == "inferred"
    assert section.holdings[0].next_event == "10/28 決算"
    assert section.holdings[1].next_event is None


def test_subset_of_configured_holdings_is_allowed():
    data = _payload()
    data["holdings"] = data["holdings"][:1]
    section = parse_holdings_section(data, holdings=HOLDINGS)
    assert len(section.holdings) == 1


def test_section_has_no_price_fields():
    # Figures are injected at render time; the LLM must have nowhere to put them.
    note_fields = set(HoldingNote.model_fields)
    assert not note_fields & {"price", "change", "change_pct", "usd_change", "jpy_change"}
    with pytest.raises(ValidationError):
        parse_holdings_section(
            _payload(holdings=[{"ticker": "TICKER1", "price": 1.0,
                                "claims": [{"text": "x", "confidence": "confirmed"}]}]),
            holdings=HOLDINGS,
        )


# --- failure ---

def test_unknown_source_id_rejected():
    data = _payload()
    data["holdings"][0]["claims"][0]["source_ids"] = ["s9"]
    with pytest.raises(ValidationError, match="s9"):
        parse_holdings_section(data, holdings=HOLDINGS)


def test_unknown_ticker_rejected():
    data = _payload()
    data["holdings"][1]["ticker"] = "NOTHELD"
    with pytest.raises(ValidationError, match="NOTHELD"):
        parse_holdings_section(data, holdings=HOLDINGS)


def test_duplicate_ticker_rejected():
    data = _payload()
    data["holdings"][1]["ticker"] = "TICKER1"
    with pytest.raises(ValidationError, match="duplicate ticker"):
        parse_holdings_section(data, holdings=HOLDINGS)


def test_duplicate_source_id_rejected():
    data = _payload()
    data["sources"].append({"id": "s1", "title": "again", "url": "https://example.com/b"})
    with pytest.raises(ValidationError, match="duplicate source id"):
        parse_holdings_section(data, holdings=HOLDINGS)


def test_invalid_confidence_rejected():
    with pytest.raises(ValidationError):
        Claim(text="x", confidence="probable")


def test_non_http_source_url_rejected():
    with pytest.raises(ValidationError):
        Source(id="s1", title="t", url="javascript:alert(1)")


def test_validation_without_holdings_context_rejected():
    # Ticker membership cannot be checked without the configured holdings.
    with pytest.raises(ValidationError, match="holdings"):
        HoldingsSection.model_validate(_payload())


# --- boundary ---

def test_empty_claim_text_rejected():
    with pytest.raises(ValidationError):
        Claim(text="", confidence="confirmed")


def test_note_without_claims_rejected():
    with pytest.raises(ValidationError):
        HoldingNote(ticker="TICKER1", claims=[])


def test_empty_holdings_list_parses():
    section = parse_holdings_section(_payload(holdings=[]), holdings=HOLDINGS)
    assert section.holdings == []


def test_claim_source_ids_default_empty():
    assert Claim(text="x", confidence="unknown").source_ids == []


# --- fixture ---

def test_briefing_fixture_validates():
    data = json.loads((FIXTURES / "holdings_2026-10-24.json").read_text(encoding="utf-8"))
    holdings = [h["ticker"] for h in data["holdings"]]
    section = parse_holdings_section(data, holdings=holdings)
    assert len(section.holdings) == 6
    assert any(c.confidence == "unknown" for h in section.holdings for c in h.claims)
