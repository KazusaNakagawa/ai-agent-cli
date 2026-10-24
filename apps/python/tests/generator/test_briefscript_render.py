import json
import pathlib

from src.fetcher.stocks import StockQuote
from src.generator.briefscript_render import (
    HOLDINGS_HEADING,
    render_holdings_markdown,
    splice_holdings,
)
from src.generator.briefscript_schema import parse_holdings_section

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "briefscript"
TICKERS = ["TICKER1", "TICKER2"]
QUOTES = {
    "TICKER1": StockQuote("TICKER1", last_price=100.0, previous_close=100.2, change_pct=-0.2),
    "TICKER2": StockQuote("TICKER2", last_price=50.0, previous_close=52.3, change_pct=-4.4),
}
FX = -0.9


def _section(data=None):
    if data is None:
        data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    return parse_holdings_section(data, holdings=TICKERS)


def _squash(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


# --- success ---

def test_sample_fixture_renders_expected_markdown():
    expected = (FIXTURES / "holdings_sample.md").read_text(encoding="utf-8")
    rendered = render_holdings_markdown(_section(), QUOTES, TICKERS, fx_change_pct=FX)
    assert _squash(rendered) == _squash(expected)


def test_heading_without_fx_shows_usd_only():
    md = render_holdings_markdown(_section(), QUOTES, TICKERS)
    assert "#### TICKER1：ドル建て ↓0.2%（$100.00）" in md


def test_non_usd_listing_shows_its_own_move_and_currency():
    quotes = dict(QUOTES, TICKER1=StockQuote("TICKER1", 2000.0, 1980.0, 1.0, "JPY"))
    md = render_holdings_markdown(_section(), quotes, TICKERS, fx_change_pct=FX)
    assert "#### TICKER1：↑1.0%（¥2000.00）" in md


def test_holdings_rendered_in_configured_order():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["holdings"].reverse()
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS, fx_change_pct=FX)
    assert md.index("TICKER1") < md.index("TICKER2")


# --- figures come only from fetcher data ---

def test_llm_text_cannot_override_heading_figures():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["holdings"][0]["claims"][0]["text"] = "#### TICKER1：ドル建て ↑99.9%（$999.99）"
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS, fx_change_pct=FX)
    headings = [line for line in md.splitlines() if line.startswith("####")]
    assert headings == [
        "#### TICKER1：ドル建て ↓0.2% / 円建て ↓1.1%（$100.00）",
        "#### TICKER2：ドル建て ↓4.4% / 円建て ↓5.3%（$50.00）",
    ]
    # The injected text is demoted to an ordinary bullet, never a heading.
    assert "- 〔推測〕#### TICKER1" not in md
    assert "↑99.9%" in md and not any("↑99.9%" in h for h in headings)


# --- failure / boundary ---

def test_failed_quote_renders_ticker_without_figures():
    quotes = dict(QUOTES, TICKER2=StockQuote("TICKER2", error="Stock fetch error (x)"))
    md = render_holdings_markdown(_section(), quotes, TICKERS, fx_change_pct=FX)
    assert "#### TICKER2：株価取得失敗" in md


def test_holding_missing_from_llm_output_is_marked_unconfirmed():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["holdings"] = data["holdings"][:1]
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS, fx_change_pct=FX)
    assert "#### TICKER2：ドル建て ↓4.4% / 円建て ↓5.3%（$50.00）" in md
    assert "- 〔未確認〕今日の材料は確認できませんでした。" in md


def test_zero_change_uses_down_arrow_like_the_fetcher():
    quotes = dict(QUOTES, TICKER1=StockQuote("TICKER1", 100.0, 100.0, 0.0))
    md = render_holdings_markdown(_section(), quotes, TICKERS)
    assert "#### TICKER1：ドル建て ↓0.0%（$100.00）" in md


# --- splice ---

_BODY = (
    "### 今日のサマリー（1文）\n\nサマリー。\n\n---\n\n"
    f"{HOLDINGS_HEADING}\n\n#### OLD：旧見出し\n- 旧本文\n\n---\n\n"
    "### 参考記事\n\n- [a](https://example.com)\n"
)


def test_splice_replaces_only_the_holdings_body():
    out = splice_holdings(_BODY, "#### NEW：新見出し\n- 新本文")
    assert "旧本文" not in out and "新本文" in out
    assert out.startswith("### 今日のサマリー（1文）")
    assert out.index(HOLDINGS_HEADING) < out.index("新本文") < out.index("### 参考記事")
    assert out.count("---") == _BODY.count("---")


def test_splice_without_holdings_heading_returns_none():
    body = "### 今日のサマリー（1文）\n\nサマリー。\n"
    assert splice_holdings(body, "#### NEW") is None


def test_splice_when_holdings_is_the_last_section():
    body = f"### 今日のサマリー（1文）\n\nx\n\n{HOLDINGS_HEADING}\n\n#### OLD\n- 旧本文\n"
    out = splice_holdings(body, "#### NEW\n- 新本文")
    assert "旧本文" not in out and out.rstrip().endswith("- 新本文")


def test_multiline_claim_cannot_open_a_new_heading():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["holdings"][0]["claims"][1]["text"] = "本文\n#### TICKER9：↑50%"
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS, fx_change_pct=FX)
    assert not any(line.startswith("#### TICKER9") for line in md.splitlines())


# --- sources, next_event, sanitisation (PR #509 review) ---

def test_sources_numbered_in_first_citation_order_and_listed():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["sources"].reverse()
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS, fx_change_pct=FX)
    assert "- ［1］[TICKER1 earnings preview]" in md
    assert md.rstrip().endswith("(https://example.com/ticker2-quarterly-results)")


def test_no_sources_means_no_source_list():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    for note in data["holdings"]:
        for claim in note["claims"]:
            claim["confidence"], claim["source_ids"] = "inferred", []
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS)
    assert "出典" not in md and "［" not in md


def test_mentions_are_neutralised():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["holdings"][0]["claims"][0]["text"] = "@everyone @here <@123> <@&456> 見て"
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS)
    assert "@everyone" not in md and "@here" not in md
    assert "<@123>" not in md and "<@&456>" not in md


def test_markdown_links_in_claims_are_flattened():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["holdings"][0]["claims"][0]["text"] = "詳細は[公式発表](https://evil.example/x)を参照"
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS)
    assert "evil.example" not in md and "詳細は公式発表を参照" in md


def test_source_title_cannot_break_its_link():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["sources"][0]["title"] = "a](https://evil.example) [b"
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS)
    assert "](https://evil.example)" not in md
    # The source is still listed, with its title escaped and its own URL.
    assert (
        "- ［1］[a］(（URL 省略） ［b](https://example.com/ticker1-earnings-preview)"
        in md.splitlines()
    )


def test_duplicate_and_padded_configured_tickers_render_once():
    md = render_holdings_markdown(_section(), QUOTES, [" TICKER1 ", "TICKER1", "TICKER2"])
    assert md.count("#### TICKER1：") == 1
    assert "#### TICKER1：ドル建て ↓0.2%（$100.00）" in md


def test_splice_stops_at_an_indented_h3():
    # CommonMark allows up to three leading spaces before a heading.
    body = (
        f"{HOLDINGS_HEADING}\n\n#### OLD\n- 旧本文\n\n"
        "   ### 参考記事\n\n- [a](https://example.com)\n\n---\n\n後続\n"
    )
    out = splice_holdings(body, "#### NEW")
    assert "旧本文" not in out
    assert "   ### 参考記事" in out and "- [a](https://example.com)" in out


def test_splice_does_not_stop_at_an_indented_code_line():
    # Four spaces is an indented code block, not a heading boundary.
    body = f"{HOLDINGS_HEADING}\n\n#### OLD\n    ### not a heading\n\n---\n\n後続\n"
    out = splice_holdings(body, "#### NEW")
    assert "not a heading" not in out and "後続" in out


def test_splice_ignores_boundaries_inside_fenced_code():
    body = (
        f"{HOLDINGS_HEADING}\n\n#### OLD\n```\n### fenced heading\n---\n```\n- 旧本文\n\n"
        "---\n\n### 参考記事\n"
    )
    out = splice_holdings(body, "#### NEW")
    assert "fenced heading" not in out and "旧本文" not in out
    assert "### 参考記事" in out


def test_splice_tilde_fence_and_unclosed_fence():
    body = f"{HOLDINGS_HEADING}\n\n~~~\n### inside\n~~~\n- 旧本文\n\n### 次\n"
    out = splice_holdings(body, "#### NEW")
    assert "inside" not in out and "### 次" in out
    # An unclosed fence swallows the rest, as CommonMark renders it.
    body = f"{HOLDINGS_HEADING}\n\n```\n### inside\n"
    assert splice_holdings(body, "#### NEW").rstrip().endswith("#### NEW")


def test_bare_urls_autolinks_and_reference_links_are_removed():
    data = json.loads((FIXTURES / "holdings_sample.json").read_text(encoding="utf-8"))
    data["holdings"][0]["claims"][0]["text"] = (
        "見て https://evil.example/a と <https://evil.example/b> と [ここ][r1] を"
    )
    md = render_holdings_markdown(_section(data), QUOTES, TICKERS)
    line = next(l for l in md.splitlines() if l.startswith("- 〔推測〕見て"))
    assert "evil.example" not in line and "[r1]" not in line
    assert line == "- 〔推測〕見て （URL 省略） と （URL 省略） と ここ を"


def test_quote_with_missing_fields_renders_as_failed():
    quotes = dict(QUOTES, TICKER1=StockQuote("TICKER1", last_price=None, change_pct=None))
    md = render_holdings_markdown(_section(), quotes, TICKERS, fx_change_pct=FX)
    assert "#### TICKER1：株価取得失敗" in md
