"""Tests for ``src.rate_check --check-upstream`` (#475).

The pricing doc is a web page, not an API contract, so the diff is advisory:
it prints, never writes the table, and never changes the exit code.
"""
from pathlib import Path

import pytest

from src import rate_check
from src.claude_rates import RATES_PATH

PRICING = Path(__file__).parent / "fixtures" / "rate_check" / "pricing_snippet.md"


@pytest.fixture
def offline_doc(monkeypatch):
    monkeypatch.setattr(rate_check, "fetch_pricing_doc", lambda: PRICING.read_text())


# --- success ---


def test_display_name_to_id():
    assert rate_check.display_name_to_id("Claude Opus 5.5") == "claude-opus-5-5"
    assert rate_check.display_name_to_id("Claude Haiku 4.5") == "claude-haiku-4-5"
    assert rate_check.display_name_to_id("Claude Opus 4.1 ([retired](https://x))") == "claude-opus-4-1"
    assert (
        rate_check.display_name_to_id("Claude Haiku 5.5 (for prompts up to 100,000 tokens)")
        == "claude-haiku-5-5"
    )


def test_parse_pricing_table_reads_only_the_main_model_table():
    upstream, tiered = rate_check.parse_pricing_table(PRICING.read_text())
    assert upstream["claude-opus-5-5"] == (4.00, 20.00, 5.00, 8.00, 0.20)
    # Footnote markers (<sup>3</sup>) are stripped from the price cells.
    assert upstream["claude-sonnet-5"] == (2.00, 10.00, 2.50, 4.00, 0.20)
    assert upstream["claude-opus-4-1"] == (15.00, 75.00, 18.75, 30.00, 1.50)
    # The batch table further down must not override the main one.
    assert len(upstream) == 5


def test_diff_upstream_reports_changes_and_gaps():
    upstream, tiered = rate_check.parse_pricing_table(PRICING.read_text())
    local = {
        "claude-opus-5-5": (4.00, 20.00, 5.00, 8.00, 0.40),  # wrong cache read
        "claude-opus-5": (5.00, 25.00, 6.25, 10.00, 0.50),  # matches
        "claude-haiku-4-5-20251001": (1.00, 5.00, 1.25, 2.00, 0.10),  # dated id
        "claude-retired-1": (1.0, 1.0, 1.0, 1.0, 1.0),  # gone upstream
    }
    text = "\n".join(rate_check.diff_upstream(local, upstream, tiered))
    assert "changed claude-opus-5-5: cache_read 0.4 -> 0.2" in text
    assert "not in pricing doc: claude-retired-1" in text
    assert "not in table: claude-opus-4-1" in text
    assert "tiered, not modelled: claude-haiku-5-5" in text
    # Matching entries, including a dated id against its family row, are silent.
    assert "claude-opus-5:" not in text
    assert "claude-haiku-4-5" not in text


def test_main_prints_the_diff_without_writing_the_table(tmp_path, offline_doc, capsys):
    before = RATES_PATH.read_bytes()
    assert rate_check.main(["--transcripts", str(tmp_path), "--check-upstream"]) == 0
    assert "tiered, not modelled: claude-haiku-5-5" in capsys.readouterr().out
    assert RATES_PATH.read_bytes() == before


# --- failure ---


def test_parse_pricing_table_without_a_table_raises():
    with pytest.raises(ValueError, match="pricing table"):
        rate_check.parse_pricing_table("# Pricing\n\nNo table here.\n")


def test_an_unreachable_doc_does_not_change_the_exit_code(tmp_path, monkeypatch, capsys):
    def _offline():
        raise OSError("network down")

    monkeypatch.setattr(rate_check, "fetch_pricing_doc", _offline)
    assert rate_check.main(["--transcripts", str(tmp_path), "--check-upstream"]) == 0
    assert "could not check: network down" in capsys.readouterr().out


# --- boundary ---


def test_diff_upstream_is_empty_when_everything_matches():
    upstream, _ = rate_check.parse_pricing_table(PRICING.read_text())
    assert rate_check.diff_upstream(dict(upstream), upstream, set()) == []


def test_upstream_is_not_fetched_without_the_flag(tmp_path, monkeypatch):
    def _fail():
        raise AssertionError("fetched without --check-upstream")

    monkeypatch.setattr(rate_check, "fetch_pricing_doc", _fail)
    assert rate_check.main(["--transcripts", str(tmp_path)]) == 0
