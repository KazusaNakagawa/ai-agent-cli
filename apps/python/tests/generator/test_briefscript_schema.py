import json
import pathlib

import pytest
from pydantic import ValidationError

from src.generator.briefscript_schema import (
    Claim,
    HoldingNote,
    HoldingsSection,
    Source,
    holdings_json_schema,
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


def test_validation_without_context_skips_only_ticker_membership():
    # A cached section must re-validate on its own; reference checks still run.
    data = _payload()
    data["holdings"][1]["ticker"] = "NOTHELD"
    assert HoldingsSection.model_validate(data).holdings[1].ticker == "NOTHELD"
    data["holdings"][0]["claims"][0]["source_ids"] = ["s9"]
    with pytest.raises(ValidationError, match="s9"):
        HoldingsSection.model_validate(data)


def test_str_holdings_rejected():
    with pytest.raises(TypeError, match="not a str"):
        parse_holdings_section(_payload(), holdings="TICKER1")


def test_confirmed_claim_without_source_rejected():
    with pytest.raises(ValidationError, match="confirmed"):
        Claim(text="x", confidence="confirmed")


def test_all_reference_errors_reported_at_once():
    data = _payload()
    data["holdings"][0]["claims"][0]["source_ids"] = ["s9"]
    data["holdings"][1]["ticker"] = "NOTHELD"
    with pytest.raises(ValidationError) as exc:
        parse_holdings_section(data, holdings=HOLDINGS)
    assert "s9" in str(exc.value) and "NOTHELD" in str(exc.value)


def test_ticker_matched_case_insensitively_and_canonicalized():
    data = _payload()
    data["holdings"][0]["ticker"] = " ticker1 "
    section = parse_holdings_section(data, holdings=HOLDINGS)
    assert section.holdings[0].ticker == "TICKER1"


def test_case_variant_duplicate_ticker_rejected():
    data = _payload()
    data["holdings"][1]["ticker"] = "ticker1"
    with pytest.raises(ValidationError, match="duplicate ticker"):
        parse_holdings_section(data, holdings=HOLDINGS)


def test_ticker_with_missing_suffix_rejected():
    with pytest.raises(ValidationError, match="7203"):
        parse_holdings_section(
            _payload(holdings=[{"ticker": "7203",
                                "claims": [{"text": "x", "confidence": "unknown"}]}]),
            holdings=["7203.T"],
        )


def test_repeated_source_id_in_claim_deduped():
    claim = Claim(text="x", confidence="confirmed", source_ids=["s1", "s1"])
    assert claim.source_ids == ["s1"]


def test_uncited_sources_dropped():
    data = _payload()
    data["sources"].append({"id": "s2", "title": "unused", "url": "https://example.com/u"})
    section = parse_holdings_section(data, holdings=HOLDINGS)
    assert [s.id for s in section.sources] == ["s1"]


def test_url_markup_in_path_is_percent_encoded():
    # HttpUrl escapes rather than rejects, which is what keeps the href safe.
    source = Source(id="s1", title="t", url='https://example.com/a"><script>')
    assert str(source.url) == "https://example.com/a%22%3E%3Cscript%3E"


def test_json_schema_pins_ticker_enum():
    schema = holdings_json_schema(HOLDINGS)
    assert schema["$defs"]["HoldingNote"]["properties"]["ticker"]["enum"] == HOLDINGS
    assert "price" not in schema["$defs"]["HoldingNote"]["properties"]


# --- boundary ---

def test_empty_claim_text_rejected():
    with pytest.raises(ValidationError):
        Claim(text="", confidence="inferred")


def test_whitespace_only_strings_rejected():
    with pytest.raises(ValidationError):
        Claim(text="   ", confidence="inferred")
    with pytest.raises(ValidationError):
        Source(id=" ", title="t", url="https://example.com")


def test_note_without_claims_rejected():
    with pytest.raises(ValidationError):
        HoldingNote(ticker="TICKER1", claims=[])


def test_empty_holdings_list_parses():
    section = parse_holdings_section(_payload(holdings=[]), holdings=HOLDINGS)
    assert section.holdings == []


def test_claim_source_ids_default_empty():
    assert Claim(text="x", confidence="unknown").source_ids == []


# --- fixture ---

def _sample() -> dict:
    return json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))


def test_sample_fixture_validates_against_configured_tickers():
    from src.config import CONFIG

    section = parse_holdings_section(_sample(), holdings=CONFIG.portfolio.tickers)
    assert [h.ticker for h in section.holdings] == ["TICKER1", "TICKER2"]
    assert {c.confidence for h in section.holdings for c in h.claims} == {
        "confirmed", "inferred", "unknown",
    }


def test_sample_fixture_rejected_when_a_ticker_is_not_configured():
    with pytest.raises(ValidationError, match="TICKER2"):
        parse_holdings_section(_sample(), holdings=["TICKER1"])


def test_more_than_three_claims_rejected():
    claims = [{"text": f"c{i}", "confidence": "inferred"} for i in range(4)]
    with pytest.raises(ValidationError):
        HoldingNote(ticker="TICKER1", claims=claims)
    schema = holdings_json_schema(HOLDINGS)
    assert schema["$defs"]["HoldingNote"]["properties"]["claims"]["maxItems"] == 3
