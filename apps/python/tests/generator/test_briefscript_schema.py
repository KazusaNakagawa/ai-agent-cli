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


# --- BriefingDocument envelope (#513) ---

from src.generator.briefscript_schema import BriefingDocument  # noqa: E402


def _doc_payload(**overrides) -> dict:
    data = {
        "date": "2026-10-24",
        "market": {"quotes": [{"ticker": "TICKER1", "last_price": 1.0, "change_pct": 0.5}],
                   "fx_change_pct": -0.9},
        "sections": [
            {"kind": "markdown", "text": "### 見出し\n\n"},
            {"kind": "holdings", "tickers": HOLDINGS, "content": _payload()},
        ],
    }
    data.update(overrides)
    return data


def test_document_parses_each_section_kind():
    doc = BriefingDocument.model_validate(_doc_payload())
    assert [s.kind for s in doc.sections] == ["markdown", "holdings"]
    assert doc.sections[1].content.holdings[0].ticker == "TICKER1"
    assert doc.version == 1


def test_document_rejects_unknown_section_kind():
    with pytest.raises(ValidationError):
        BriefingDocument.model_validate(_doc_payload(sections=[{"kind": "slides", "text": "x"}]))


def test_document_rejects_unknown_fields_and_versions():
    with pytest.raises(ValidationError):
        BriefingDocument.model_validate(_doc_payload(extra=1))
    with pytest.raises(ValidationError):
        BriefingDocument.model_validate(_doc_payload(version=2))


def test_document_keeps_markdown_whitespace():
    doc = BriefingDocument.model_validate(
        _doc_payload(sections=[{"kind": "markdown", "text": "\n\n---\n\n"}])
    )
    assert doc.sections[0].text == "\n\n---\n\n"


def test_document_holdings_content_is_still_cross_checked():
    data = _doc_payload()
    data["sections"][1]["content"]["holdings"][0]["claims"][0]["source_ids"] = ["s9"]
    with pytest.raises(ValidationError, match="s9"):
        BriefingDocument.model_validate(data)


def test_document_minimal_and_failed_holdings():
    doc = BriefingDocument.model_validate({"date": "2026-10-24"})
    assert doc.sections == [] and doc.market.quotes == []
    doc = BriefingDocument.model_validate(
        _doc_payload(sections=[{"kind": "holdings", "tickers": HOLDINGS}])
    )
    assert doc.sections[0].content is None


# --- sectors (#514) ---

from src.generator.briefscript_schema import (  # noqa: E402
    SectorNote,
    parse_sectors_section,
    sectors_json_schema,
)

SECTORS = ["AI・クラウド", "防衛"]


def _sectors(**overrides) -> dict:
    data = {
        "sectors": [
            {"sector": "AI・クラウド", "claims": [
                {"text": "投資が拡大。", "confidence": "confirmed", "source_ids": ["s1"]},
            ], "related_tickers": ["MSFT"]},
            {"sector": "防衛", "claims": []},
        ],
        "sources": [{"id": "s1", "title": "t", "url": "https://example.com/s1"}],
    }
    data.update(overrides)
    return data


def test_sectors_payload_parses_with_quiet_sector():
    section = parse_sectors_section(_sectors(), sectors=SECTORS)
    assert [n.sector for n in section.sectors] == SECTORS
    assert section.sectors[1].claims == []


def test_sector_name_whitespace_is_canonicalised():
    data = _sectors()
    data["sectors"][1]["sector"] = "防衛 "
    section = parse_sectors_section(data, sectors=[" AI・クラウド", "防衛"])
    assert [n.sector for n in section.sectors] == SECTORS


def test_unknown_and_duplicate_sectors_rejected_together():
    data = _sectors()
    data["sectors"].append({"sector": "宇宙", "claims": []})
    data["sectors"].append({"sector": "防衛", "claims": []})
    with pytest.raises(ValidationError) as exc:
        parse_sectors_section(data, sectors=SECTORS)
    assert "宇宙" in str(exc.value) and "duplicate sector" in str(exc.value)


def test_sector_unknown_source_rejected_and_uncited_dropped():
    data = _sectors()
    data["sectors"][0]["claims"][0]["source_ids"] = ["s9"]
    with pytest.raises(ValidationError, match="s9"):
        parse_sectors_section(data, sectors=SECTORS)
    data = _sectors()
    data["sources"].append({"id": "s2", "title": "u", "url": "https://example.com/u"})
    assert [s.id for s in parse_sectors_section(data, sectors=SECTORS).sources] == ["s1"]


def test_sector_bounds():
    with pytest.raises(ValidationError):
        SectorNote(sector="x", claims=[{"text": f"c{i}", "confidence": "inferred"} for i in range(4)])
    with pytest.raises(ValidationError):
        SectorNote(sector="x", related_tickers=[f"T{i}" for i in range(6)])
    with pytest.raises(ValidationError):
        SectorNote(sector=" ")


def test_sectors_schema_pins_names_and_rejects_str():
    schema = sectors_json_schema(SECTORS)
    assert schema["$defs"]["SectorNote"]["properties"]["sector"]["enum"] == SECTORS
    with pytest.raises(TypeError):
        sectors_json_schema("防衛")
    with pytest.raises(TypeError):
        parse_sectors_section(_sectors(), sectors="防衛")


def test_document_accepts_a_sectors_block():
    doc = BriefingDocument.model_validate(_doc_payload(sections=[
        {"kind": "sectors", "sectors": SECTORS, "content": _sectors()},
    ]))
    assert doc.sections[0].content.sectors[0].sector == "AI・クラウド"


# --- main analysis (#515) ----------------------------------------------------

from src.generator.briefscript_schema import MainSection, main_json_schema, parse_main_section  # noqa: E402

CONFLICTS = ["リスクA", "リスクB"]


def _parse_main(data):
    return parse_main_section(data, conflicts=CONFLICTS)


def _main(**overrides) -> dict:
    data = {
        "summary": "今日のまとめ。",
        "stories": [{"title": "話題A", "claims": [
            {"text": "事実。", "confidence": "confirmed", "source_ids": ["s1"]},
            {"text": "見立て。", "confidence": "inferred"},
        ]}],
        "geopolitics": [{"risk": "リスクA", "impact": {
            "text": "影響。", "confidence": "confirmed", "source_ids": ["s2"]}, "related": ["SECTOR1"]}],
        "fx": {"claims": [{"text": "水準の意味。", "confidence": "inferred"}]},
        "references": [{"category": "カテゴリA", "source_ids": ["s1", "s2"]}],
        "sources": [
            {"id": "s1", "title": "t1", "url": "https://example.com/1"},
            {"id": "s2", "title": "t2", "url": "https://example.com/2"},
        ],
    }
    data.update(overrides)
    return data


def test_main_payload_parses():
    section = _parse_main(_main())
    assert [c.text for c in section.claims()] == ["事実。", "見立て。", "影響。", "水準の意味。"]
    assert [s.id for s in section.sources] == ["s1", "s2"]


def test_main_minimal_payload_parses():
    section = _parse_main(_main(geopolitics=[], fx={"claims": []}, references=[], sources=[],
                                       stories=[{"title": "T", "claims": [{"text": "x", "confidence": "unknown"}]}]))
    assert section.geopolitics == [] and section.fx.claims == [] and section.references == []


@pytest.mark.parametrize("where", ["stories", "geopolitics", "fx"])
def test_main_confirmed_claim_without_source_rejected(where):
    data = _main()
    bare = {"text": "x", "confidence": "confirmed"}
    if where == "stories":
        data["stories"][0]["claims"][0] = bare
    elif where == "geopolitics":
        data["geopolitics"][0]["impact"] = bare
    else:
        data["fx"]["claims"][0] = bare
    with pytest.raises(ValidationError, match="must cite at least one source"):
        _parse_main(data)


def test_main_fx_has_no_rate_field():
    with pytest.raises(ValidationError, match="extra"):
        _parse_main(_main(fx={"rate": 160.0, "claims": []}))
    assert "rate" not in main_json_schema(CONFLICTS)["$defs"]["FxNote"]["properties"]


def test_main_reference_errors_reported_at_once():
    data = _main(references=[{"category": "C", "source_ids": ["s7"]}])
    data["stories"][0]["claims"][0]["source_ids"] = ["s9"]
    data["sources"].append({"id": "s1", "title": "dup", "url": "https://example.com/d"})
    with pytest.raises(ValidationError) as e:
        _parse_main(data)
    msg = str(e.value)
    assert "s9" in msg and "s7" in msg and "duplicate source id: s1" in msg


def test_main_references_list_only_cited_sources():
    data = _main(references=[
        {"category": "A", "source_ids": ["s2", "s3"]},
        {"category": "B", "source_ids": ["s2", "s3"]},
        {"category": "C", "source_ids": ["s3"]},
    ])
    data["sources"].append({"id": "s3", "title": "uncited", "url": "https://example.com/3"})
    section = _parse_main(data)
    assert [s.id for s in section.sources] == ["s1", "s2"]
    # s3 is uncited; s2 stays in its first group only; empty groups go.
    assert [(g.category, g.source_ids) for g in section.references] == [("A", ["s2"])]


def test_main_bounds():
    story = {"title": "T", "claims": [{"text": "x", "confidence": "inferred"}]}
    _parse_main(_main(stories=[story] * 4))
    for bad in ([], [story] * 5, [{"title": "T", "claims": []}]):
        with pytest.raises(ValidationError):
            _parse_main(_main(stories=bad))
    with pytest.raises(ValidationError):
        _parse_main(_main(summary=" "))


def test_document_accepts_a_main_block_and_fx_context():
    doc = BriefingDocument.model_validate({
        "date": "2026-10-25",
        "market": {"fx_context": "- USD/JPY: 150.00"},
        "sections": [{"kind": "main", "content": _main(), "holdings": {"kind": "holdings", "tickers": ["T"]}}],
    })
    assert isinstance(doc.sections[0].content, MainSection)
    assert doc.market.fx_context == "- USD/JPY: 150.00"


def test_main_geopolitics_rows_are_configured_conflicts():
    row = _main()["geopolitics"][0]
    section = _parse_main(_main(geopolitics=[{**row, "risk": " リスクB "}]))
    assert section.geopolitics[0].risk == "リスクB"
    with pytest.raises(ValidationError) as e:
        _parse_main(_main(geopolitics=[row, row, {**row, "risk": "未設定"}]))
    assert "duplicate risk: リスクA" in str(e.value) and "未設定" in str(e.value)


def test_main_geopolitics_bound_follows_the_config():
    many = [f"紛争{i}" for i in range(8)]
    rows = [{"risk": name, "impact": {"text": "x", "confidence": "inferred"}} for name in many]
    assert len(parse_main_section(_main(geopolitics=rows), conflicts=many).geopolitics) == 8
    schema = main_json_schema(many)
    assert schema["properties"]["geopolitics"]["maxItems"] == 8
    assert schema["$defs"]["GeoImpact"]["properties"]["risk"]["enum"] == many
    empty = main_json_schema([])
    assert empty["properties"]["geopolitics"]["maxItems"] == 0
    assert "enum" not in empty["$defs"]["GeoImpact"]["properties"]["risk"]
    with pytest.raises(TypeError):
        main_json_schema("リスクA")
