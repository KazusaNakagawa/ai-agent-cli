import pathlib
import re

from src.generator.briefscript_notion import render_document_notion
from src.generator.briefscript_render import render_document_markdown
from src.generator.briefscript_schema import (
    BriefingDocument,
    HoldingsBlock,
    MainBlock,
    MarketSnapshot,
    MarkdownSection,
    SectorsBlock,
    parse_holdings_section,
    parse_main_section,
    parse_sectors_section,
)
from src.notifier.markdown import markdown_to_notion_blocks

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "briefscript"
_FX = "- USD/JPY: 150.23（前日比 +0.10%）\n    - 140円: -4.00%"


def _main(**overrides) -> dict:
    data = {
        "summary": "今日のまとめ。",
        "stories": [{"title": "話題A", "claims": [
            {"text": "事実A。", "confidence": "confirmed", "source_ids": ["s1"]},
            {"text": "見立てB。", "confidence": "inferred"},
        ]}],
        "geopolitics": [{"risk": "リスクA", "impact": {
            "text": "影響。", "confidence": "confirmed", "source_ids": ["s2"]}, "related": ["S1", "S2"]}],
        "fx": {"claims": [{"text": "理由は不明。", "confidence": "unknown"}]},
        "references": [{"category": "カテゴリA", "source_ids": ["s2"]}],
        "sources": [
            {"id": "s1", "title": "記事1", "url": "https://example.com/1"},
            {"id": "s2", "title": "記事2", "url": "https://example.com/2"},
        ],
    }
    data.update(overrides)
    return data


def _holdings(text="保有の事実。") -> HoldingsBlock:
    return HoldingsBlock(tickers=["T1", "T2"], content=parse_holdings_section({
        "holdings": [{"ticker": "T1", "claims": [
            {"text": text, "confidence": "confirmed", "source_ids": ["h1"]}], "next_event": "決算"}],
        "sources": [{"id": "h1", "title": "保有記事", "url": "https://example.com/h1"}],
    }, holdings=["T1", "T2"]))


def _sectors() -> SectorsBlock:
    return SectorsBlock(sectors=["Sec1", "Sec2", "Sec3"], content=parse_sectors_section({
        "sectors": [
            {"sector": "Sec1", "claims": [
                {"text": "投資拡大。", "confidence": "confirmed", "source_ids": ["x1"]}],
             "related_tickers": ["A", "B"]},
            {"sector": "Sec2", "claims": []},
        ],
        "sources": [{"id": "x1", "title": "セクター記事", "url": "https://example.com/x1"}],
    }, sectors=["Sec1", "Sec2", "Sec3"]))


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        quotes=[{"ticker": "T1", "last_price": 10.0, "change_pct": 1.0},
                {"ticker": "T2", "last_price": 20.0, "change_pct": -2.0}],
        fx_change_pct=-0.5, fx_context=_FX,
    )


def _doc(*sections) -> BriefingDocument:
    return BriefingDocument(date="2026-10-25", market=_market(), sections=list(sections))


def _full_doc() -> BriefingDocument:
    return _doc(
        MainBlock(content=parse_main_section(_main(), conflicts=["リスクA"]), holdings=_holdings()),
        MarkdownSection(text="\n\n---\n\n## セクター動向\n\n"),
        _sectors(),
    )


def _plain_text(block: dict) -> str:
    return "".join(r["text"]["content"] for r in block[block["type"]].get("rich_text", []))


def _headings(blocks: list[dict]) -> list[str]:
    return [_plain_text(b) for b in blocks if b["type"].startswith("heading_")]


def _md_headings(markdown: str) -> list[str]:
    # Only real "#" headings: the Markdown converter also promotes "label：" and
    # "**出典**" lines to headings, which the native blocks keep as text.
    return [re.sub(r"^#+\s*", "", line) for line in markdown.splitlines() if line.startswith("#")]


def _links(blocks: list[dict]) -> list[str]:
    urls = []
    for block in blocks:
        body = block[block["type"]]
        rich = list(body.get("rich_text", []))
        for row in body.get("children", []):
            for cell in row.get("table_row", {}).get("cells", []):
                rich += cell
        urls += [r["text"]["link"]["url"] for r in rich if r["text"].get("link")]
    return urls


def _find(blocks, text):
    return next(b for b in blocks if _plain_text(b) == text)


def test_headings_match_the_markdown_version():
    doc = _full_doc()
    assert _headings(render_document_notion(doc)) == _md_headings(render_document_markdown(doc))


def test_source_links_match_the_markdown_version():
    doc = _full_doc()
    md_links = set(_links(markdown_to_notion_blocks(render_document_markdown(doc))))
    assert set(_links(render_document_notion(doc))) == md_links
    assert md_links == {"https://example.com/1", "https://example.com/2",
                        "https://example.com/h1", "https://example.com/x1"}


def test_summary_is_a_callout_and_parts_are_divided():
    blocks = render_document_notion(_full_doc())
    assert blocks[0]["type"] == "heading_3"
    assert blocks[1]["type"] == "callout" and _plain_text(blocks[1]) == "今日のまとめ。"
    # summary | stories | geopolitics | fx | holdings | references, then the sectors rule.
    assert [b["type"] for b in blocks].count("divider") == 6


def test_claims_carry_a_coloured_label_and_linked_markers():
    blocks = render_document_notion(_full_doc())
    confirmed = _find(blocks, "事実A。［1］")["bulleted_list_item"]["rich_text"]
    assert confirmed[0]["text"] == {"content": "事実A。"}
    assert confirmed[1]["text"] == {"content": "［1］", "link": {"url": "https://example.com/1"}}
    inferred = _find(blocks, "〔推測〕見立てB。")["bulleted_list_item"]["rich_text"]
    assert inferred[0]["annotations"] == {"color": "orange"}
    unknown = _find(blocks, "〔未確認〕理由は不明。")["bulleted_list_item"]["rich_text"]
    assert unknown[0]["annotations"] == {"color": "gray"}


def test_geopolitics_is_a_table_with_header():
    table = next(b for b in render_document_notion(_full_doc()) if b["type"] == "table")["table"]
    assert table["table_width"] == 3 and table["has_column_header"] is True
    header, row = (r["table_row"]["cells"] for r in table["children"])
    assert ["".join(i["text"]["content"] for i in c) for c in header] == [
        "地政学リスク", "今日の影響", "関連銘柄・セクター"]
    assert ["".join(i["text"]["content"] for i in c) for c in row] == ["リスクA", "影響。［2］", "S1, S2"]


def test_fx_block_is_the_fetcher_text():
    blocks = render_document_notion(_full_doc())
    fx = _find(blocks, "USD/JPY: 150.23（前日比 +0.10%）")
    assert fx["type"] == "bulleted_list_item"
    child = fx["bulleted_list_item"]["children"][0]
    assert _plain_text(child) == "140円: -4.00%"


def test_holdings_inside_main_are_numbered_after_the_main_sources():
    blocks = render_document_notion(_full_doc())
    heading = _find(blocks, "T1：ドル建て ↑1.0% / 円建て ↑0.5%（$10.00）")
    assert heading["type"] == "heading_3"
    assert _find(blocks, "保有の事実。［3］")
    assert _find(blocks, "次の予定：決算")
    assert _find(blocks, "T2：ドル建て ↓2.0% / 円建て ↓2.5%（$20.00）")
    assert _find(blocks, "〔未確認〕今日の材料は確認できませんでした。")
    source = _find(blocks, "［3］保有記事")["bulleted_list_item"]["rich_text"]
    assert source[1]["text"]["link"] == {"url": "https://example.com/h1"}


def test_references_are_grouped_with_ungrouped_last():
    headings = _headings(render_document_notion(_full_doc()))
    i = headings.index("参考記事")
    assert headings[i + 1:i + 3] == ["カテゴリA", "その他"]


def test_sectors_cover_quiet_and_missing_sectors():
    blocks = render_document_notion(_doc(_sectors()))
    assert _headings(blocks) == ["今日のセクター動向（全セクター）", "Sec1", "Sec2", "Sec3"]
    texts = [_plain_text(b) for b in blocks]
    assert "投資拡大。［1］" in texts and "関連銘柄：A, B" in texts
    assert "動き限定的" in texts and "〔未確認〕今日の動きは確認できませんでした。" in texts
    assert texts[-2:] == ["出典", "［1］セクター記事"]


def test_failed_holdings_block_shows_the_failure_note():
    blocks = render_document_notion(_doc(HoldingsBlock(tickers=["T1"])))
    assert [_plain_text(b) for b in blocks] == [
        "T1：ドル建て ↑1.0% / 円建て ↑0.5%（$10.00）", "〔未確認〕本日の示唆は生成できませんでした。"]


def test_markdown_section_goes_through_the_markdown_converter():
    text = "⚠️ 失敗\n\n---\n\n## セクター動向\n\n- [a](https://example.com/a)"
    assert render_document_notion(_doc(MarkdownSection(text=text))) == markdown_to_notion_blocks(text)


def test_claim_over_2000_characters_is_split_into_rich_text_items():
    long = "長" * 4500
    blocks = render_document_notion(_doc(_holdings(text=long)))
    rich = _find(blocks, long + "［1］")["bulleted_list_item"]["rich_text"]
    assert [len(r["text"]["content"]) for r in rich] == [2000, 2000, 500, 3]
    assert all(len(r["text"]["content"]) <= 2000 for b in blocks for r in b[b["type"]].get("rich_text", []))


def test_model_text_is_flattened():
    data = _main(summary="## [x](https://evil.example) @everyone")
    doc = _doc(MainBlock(content=parse_main_section(data, conflicts=["リスクA"])))
    callout = render_document_notion(doc)[1]
    assert _plain_text(callout) == "x ＠everyone"
    assert "evil.example" not in str(render_document_notion(doc))


def test_golden_document_matches_its_markdown_headings_and_links():
    doc = BriefingDocument.model_validate_json(
        (FIXTURES / "briefing_document.json").read_text(encoding="utf-8")
    )
    markdown = render_document_markdown(doc)
    blocks = render_document_notion(doc)
    assert _headings(blocks) == _md_headings(markdown)
    assert set(_links(blocks)) == set(_links(markdown_to_notion_blocks(markdown)))
    assert not any(re.search(r"\*\*", _plain_text(b)) for b in blocks if b["type"] != "table")
