import pathlib
import re

import pytest

from src.generator.briefscript_schema import (
    HoldingsBlock,
    MainBlock,
    MarkdownSection,
    SectorsBlock,
    parse_main_section,
    parse_sectors_section,
)
from src.generator.briefscript_slides import render_document_slides
from tests.generator.test_briefscript_notion import _doc, _full_doc, _main
from tests.generator.test_briefscript_speech import _golden

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "briefscript"


def _slides(deck: str) -> list[str]:
    """Slide bodies after the front matter."""
    front, *slides = deck.split("\n---\n")
    assert "marp: true" in front
    return [s.strip() for s in slides]


def test_golden_fixture_renders_the_expected_deck():
    expected = (FIXTURES / "briefing_document.slides.md").read_text(encoding="utf-8")
    assert render_document_slides(_golden()) == expected


def test_deck_opens_with_marp_front_matter_and_a_title_slide():
    deck = render_document_slides(_full_doc())
    assert deck.startswith("---\nmarp: true\n")
    assert _slides(deck)[0] == "# マーケットブリーフィング\n\n2026-10-25"


def test_each_section_and_holding_gets_its_own_slide():
    headings = [s.splitlines()[0] for s in _slides(render_document_slides(_full_doc()))]
    assert headings == [
        "# マーケットブリーフィング",
        "## 今日のサマリー",
        "## 話題A",
        "## 地政学と株式の因果関係",
        "## 為替",
        "## T1：ドル建て ↑1.0% / 円建て ↑0.5%（$10.00）",
        "## T2：ドル建て ↓2.0% / 円建て ↓2.5%（$20.00）",
        "## セクター動向",
        "## 出典",
    ]


def _count_claims(slide: str) -> int:
    # Claims are the bullets that are neither source items nor labelled lines.
    return sum(
        1 for line in slide.splitlines()
        if line.startswith("- ") and not line.startswith("- ［")
        and not line.startswith(("- 次の予定：", "- 動き限定的："))
    )


@pytest.mark.parametrize("max_claims", [1, 2, 3])
def test_no_slide_exceeds_the_claim_cap(max_claims):
    many = [{"text": f"主張{i}。", "confidence": "inferred"} for i in range(4)]
    main = _main(stories=[{"title": "多い話題", "claims": many}])
    sectors = SectorsBlock(sectors=[f"S{i}" for i in range(5)], content=parse_sectors_section({
        "sectors": [{"sector": f"S{i}", "claims": [{"text": f"動き{i}。", "confidence": "inferred"}]}
                    for i in range(5)],
    }, sectors=[f"S{i}" for i in range(5)]))
    doc = _doc(MainBlock(content=parse_main_section(main, conflicts=["リスクA"])), sectors)

    slides = _slides(render_document_slides(doc, max_claims=max_claims))
    assert all(_count_claims(s) <= max_claims for s in slides)
    # Every sector is still on some slide; the cap splits, it does not drop.
    assert all(any(f"S{i}：" in s for s in slides) for i in range(5))


def test_capped_story_claims_are_cut_and_their_sources_not_listed():
    claims = [
        {"text": "残る。", "confidence": "confirmed", "source_ids": ["s1"]},
        {"text": "落ちる。", "confidence": "confirmed", "source_ids": ["s2"]},
    ]
    main = _main(stories=[{"title": "話題", "claims": claims}], geopolitics=[], references=[])
    deck = render_document_slides(_doc(MainBlock(content=parse_main_section(main, conflicts=[]))), max_claims=1)
    assert "残る。［1］" in deck and "落ちる" not in deck
    assert "記事1" in deck and "記事2" not in deck


def test_confidence_markers_and_sources_are_numbered_across_the_deck():
    deck = render_document_slides(_full_doc())
    assert "- 〔推測〕見立てB。" in deck
    assert "- 事実A。［1］" in deck
    sources = _slides(deck)[-1]
    assert sources.splitlines()[0] == "## 出典"
    assert "- ［1］[記事1](https://example.com/1)" in sources
    numbers = [int(n) for n in re.findall(r"^- ［(\d+)］", sources, flags=re.M)]
    assert numbers == list(range(1, len(numbers) + 1))


def test_sectors_list_quiet_ones_and_skip_missing():
    slide = next(s for s in _slides(render_document_slides(_full_doc())) if s.startswith("## セクター"))
    assert "- Sec1：投資拡大。" in slide
    assert "- 動き限定的：Sec2" in slide
    assert "Sec3" not in slide


def test_failed_holdings_call_still_gets_a_slide_per_ticker():
    slides = _slides(render_document_slides(_doc(HoldingsBlock(tickers=["T1", "T2"], content=None))))
    assert [s.splitlines()[0][:5] for s in slides[1:]] == ["## T1", "## T2"]
    assert "本日の示唆は生成できませんでした" in slides[1]


def test_markdown_passthrough_is_left_out():
    deck = render_document_slides(_doc(MarkdownSection(text="## 失敗しました\n")))
    assert "失敗しました" not in deck
    assert len(_slides(deck)) == 1


def test_no_sources_means_no_sources_slide():
    deck = render_document_slides(_doc(HoldingsBlock(tickers=["T1"], content=None)))
    assert "## 出典" not in deck


def test_model_text_cannot_split_or_style_the_deck():
    def deck_for(summary: str) -> str:
        main = _main(summary=summary)
        return render_document_slides(_doc(MainBlock(content=parse_main_section(main, conflicts=["リスクA"]))))

    deck = deck_for("前半\n\n---\n\n# 乗っ取り <style>x</style> [リンク](https://evil.example)")
    assert "\n# 乗っ取り" not in deck and "evil.example" not in deck
    assert "<style>" not in deck
    assert len(_slides(deck)) == len(_slides(deck_for("普通の要約。")))


def test_max_claims_below_one_is_rejected():
    with pytest.raises(ValueError):
        render_document_slides(_full_doc(), max_claims=0)
