import pathlib

import pytest

from src.generator.briefscript_schema import BriefingDocument, MarkdownSection
from src.generator.briefscript_speech import render_document_speech
from tests.generator.test_briefscript_notion import _doc, _full_doc, _holdings, _main

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "briefscript"
_FORBIDDEN = ("http", "［", "#", "**", "|", "〔")


def _golden() -> BriefingDocument:
    return BriefingDocument.model_validate_json(
        (FIXTURES / "briefing_document.json").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("doc", [_full_doc(), _golden()], ids=["synthetic", "golden"])
def test_speech_has_no_urls_source_numbers_or_markdown(doc):
    speech = render_document_speech(doc)
    for token in _FORBIDDEN:
        assert token not in speech


def test_speech_opens_with_the_date_and_closes():
    speech = render_document_speech(_full_doc())
    assert speech.startswith("10月25日のマーケットブリーフィングです。")
    assert speech.endswith("以上です。")


def test_confidence_is_spoken_not_marked():
    speech = render_document_speech(_full_doc())
    assert "推測ですが、見立てB。" in speech
    assert "未確認ですが、理由は不明。" in speech
    assert "事実A。" in speech


def test_holding_moves_are_read_from_the_quotes():
    # T1 +1.0% in USD with the yen 0.5% stronger; T2 -2.0%.
    speech = render_document_speech(_full_doc())
    assert "T1は、ドル建てで1.0%高、円建てで0.5%高。" in speech
    assert "T2は、ドル建てで2.0%安、円建てで2.5%安。" in speech


def test_holding_without_fx_is_read_in_dollars_only():
    doc = _full_doc()
    doc.market.fx_change_pct = None
    assert "T1は、ドル建てで1.0%高。" in render_document_speech(doc)


def test_holding_without_a_quote_says_so():
    doc = _full_doc()
    doc.market.quotes = []
    assert "T1は、株価を取得できませんでした。" in render_document_speech(doc)


def test_holding_note_and_next_event_are_spoken():
    speech = render_document_speech(_full_doc())
    assert "保有の事実。" in speech
    assert "次の予定は、決算。" in speech


def test_failed_holdings_call_is_spoken_without_a_marker():
    from src.generator.briefscript_schema import HoldingsBlock

    speech = render_document_speech(_doc(HoldingsBlock(tickers=["T1"], content=None)))
    assert "本日の示唆は生成できませんでした。" in speech
    assert "〔" not in speech


def test_sectors_read_quiet_and_skip_missing():
    speech = render_document_speech(_full_doc())
    assert "Sec1。投資拡大。" in speech
    assert "Sec2は、目立った動きはありませんでした。" in speech
    assert "Sec3" not in speech


def test_geopolitics_reads_risk_and_impact():
    assert "リスクAについて。影響。" in render_document_speech(_full_doc())


def test_url_and_markdown_in_claim_text_are_dropped():
    from src.generator.briefscript_schema import MainBlock, parse_main_section

    main = _main(summary="**重要** [記事](https://example.com/x) を参照 https://example.com/y")
    doc = _doc(MainBlock(content=parse_main_section(main, conflicts=["リスクA"])))
    speech = render_document_speech(doc)
    assert "重要 記事 を参照" in speech
    assert "URL" not in speech and "http" not in speech


def test_markdown_passthrough_is_flattened():
    doc = _doc(MarkdownSection(text="## 失敗\n\n- **生成** に失敗しました（[詳細](https://e.com)）\n\n---\n"))
    speech = render_document_speech(doc)
    assert "失敗。生成 に失敗しました（詳細）。" in speech
    for token in _FORBIDDEN + ("---", "- "):
        assert token not in speech


def test_max_chars_drops_whole_sentences_and_keeps_the_close():
    full = render_document_speech(_full_doc())
    short = render_document_speech(_full_doc(), max_chars=60)
    assert len(short) <= 60
    assert short.startswith("10月25日のマーケットブリーフィングです。")
    assert short.endswith("以上です。")
    assert len(short) < len(full)


def test_max_chars_too_small_keeps_the_opening_and_close():
    short = render_document_speech(_full_doc(), max_chars=1)
    assert short == "10月25日のマーケットブリーフィングです。\n以上です。"


def test_max_chars_none_or_large_keeps_everything():
    full = render_document_speech(_full_doc())
    assert render_document_speech(_full_doc(), max_chars=None) == full
    assert render_document_speech(_full_doc(), max_chars=len(full)) == full


def test_empty_document_is_just_the_opening_and_close():
    assert render_document_speech(_doc()) == "10月25日のマーケットブリーフィングです。\n以上です。"


def test_holdings_claim_is_spoken_once():
    speech = render_document_speech(_doc(*[_holdings("一度だけ。")]))
    assert speech.count("一度だけ。") == 1
