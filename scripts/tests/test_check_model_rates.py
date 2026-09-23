"""Tests for scripts/check_model_rates.py.

The checker exists because claude-opus-5 sat unpriced for three weeks and the
only signal was an amber line in the UI. It has two jobs: notice a model that
shows up in transcripts with no rates, and notice when the rates we do have
stop matching what Claude Code itself recorded paying.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_model_rates as cmr  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
RATE_FIELDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")

# Real rates, duplicated here so a test failure says which side moved.
OPUS_5 = {"input": 5.0, "output": 25.0, "cache_write_5m": 6.25,
          "cache_write_1h": 10.0, "cache_read": 0.5}
HAIKU = {"input": 1.0, "output": 5.0, "cache_write_5m": 1.25,
         "cache_write_1h": 2.0, "cache_read": 0.1}


@pytest.fixture
def rates_file(tmp_path: Path):
    def _write(rates: dict) -> Path:
        path = tmp_path / "model_rates.json"
        path.write_text(json.dumps({"rates": rates}))
        return path

    return _write


def _usage_line(model: str, ts: str = "2026-09-01T03:00:00.000Z") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": ts,
            "message": {
                "id": f"msg_{model}",
                "model": model,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        }
    )


def _cost_state_line(model_usage: dict) -> str:
    return json.dumps({"type": "cost-state", "modelUsage": model_usage})


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def transcripts(tmp_path: Path) -> Path:
    return tmp_path / "projects"


# --- unpriced models ---


def test_a_model_in_transcripts_without_rates_fails(transcripts, rates_file, capsys):
    _write(transcripts / "p" / "s.jsonl", [_usage_line("claude-opus-5")])

    code = cmr.main(["--transcripts", str(transcripts), "--rates", str(rates_file({}))])

    assert code == 1
    assert "claude-opus-5" in capsys.readouterr().out


def test_a_fully_priced_transcript_passes(transcripts, rates_file, capsys):
    _write(transcripts / "p" / "s.jsonl", [_usage_line("claude-opus-5")])

    code = cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-opus-5": OPUS_5}))]
    )

    assert code == 0
    assert "OK" in capsys.readouterr().out


def test_synthetic_is_not_reported_as_missing(transcripts, rates_file):
    # CLI-internal messages carry no tokens and are never priced.
    _write(transcripts / "p" / "s.jsonl", [_usage_line("<synthetic>")])

    assert cmr.main(["--transcripts", str(transcripts), "--rates", str(rates_file({}))]) == 0


# --- reconciliation against cost-state ground truth ---


def test_matching_rates_reconcile(transcripts, rates_file):
    # cacheCreation is reported without its TTL split, so the check brackets
    # the cost between an all-5m and an all-1h read of the same write tokens.
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-opus-5": {
            "inputTokens": 8, "outputTokens": 1466, "cacheReadInputTokens": 172820,
            "cacheCreationInputTokens": 27649, "webSearchRequests": 0,
            "costUSD": 0.39959000000000006}})],
    )

    assert cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-opus-5": OPUS_5}))]
    ) == 0


def test_a_perturbed_rate_is_caught(transcripts, rates_file, capsys):
    # A record with no cache writes has no TTL ambiguity, so the bracket
    # collapses to a point and even a small rate error shows.
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-haiku-4-5-20251001": {
            "inputTokens": 2760, "outputTokens": 45, "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0, "webSearchRequests": 0,
            "costUSD": 0.002985}})],
    )
    wrong = {**HAIKU, "output": 8.0}

    code = cmr.main(
        ["--transcripts", str(transcripts),
         "--rates", str(rates_file({"claude-haiku-4-5-20251001": wrong}))]
    )

    assert code == 1
    out = capsys.readouterr().out
    assert "claude-haiku-4-5-20251001" in out and "0.0030" in out


def test_an_error_smaller_than_the_cache_write_bracket_is_not_flagged(
    transcripts, rates_file
):
    # Known blind spot, asserted so it stays a deliberate limit rather than a
    # surprise: modelUsage does not carry the 5m/1h split, so on a record with
    # cache writes any error that fits inside the two-rate spread is invisible.
    # Sensitivity therefore depends on having records with few or no writes.
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-opus-5": {
            "inputTokens": 8, "outputTokens": 1466, "cacheReadInputTokens": 172820,
            "cacheCreationInputTokens": 27649, "webSearchRequests": 0,
            "costUSD": 0.39959000000000006}})],
    )
    wrong = {**OPUS_5, "cache_read": 0.75}

    assert cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-opus-5": wrong}))]
    ) == 0


def test_an_error_larger_than_the_bracket_is_still_caught_with_cache_writes(
    transcripts, rates_file
):
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-opus-5": {
            "inputTokens": 8, "outputTokens": 1466, "cacheReadInputTokens": 172820,
            "cacheCreationInputTokens": 27649, "webSearchRequests": 0,
            "costUSD": 0.39959000000000006}})],
    )
    wrong = {**OPUS_5, "cache_read": 5.0}

    assert cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-opus-5": wrong}))]
    ) == 1


def test_real_cost_state_fixtures_reconcile_against_the_shipped_table():
    # Guards the shipped config/model_rates.json against records Claude Code
    # actually wrote, so the table cannot drift unnoticed.
    from src.claude_rates import RATES_PATH

    code = cmr.main(["--transcripts", str(FIXTURES), "--rates", str(RATES_PATH)])

    assert code == 0


# --- boundary / tolerated gaps ---


def test_a_mixed_ttl_session_between_the_two_write_rates_passes(transcripts, rates_file):
    # This real session's writes were ~60% 1-hour, so its cost sits between the
    # all-5m and all-1h brackets. Neither endpoint matches; the bracket does.
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-opus-5": {
            "inputTokens": 4554, "outputTokens": 18247, "cacheReadInputTokens": 1954640,
            "cacheCreationInputTokens": 104748, "webSearchRequests": 0,
            "costUSD": 2.3486262499999997}})],
    )

    assert cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-opus-5": OPUS_5}))]
    ) == 0


def test_rows_with_web_search_requests_are_skipped(transcripts, rates_file, capsys):
    # Web search bills $0.01 per request on top of tokens and is not modelled,
    # so such a row would otherwise read as permanent drift.
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-haiku-4-5-20251001": {
            "inputTokens": 46758, "outputTokens": 2512, "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0, "webSearchRequests": 5,
            "costUSD": 0.109318}})],
    )

    code = cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-haiku-4-5-20251001": HAIKU}))]
    )

    assert code == 0
    assert "skipped" in capsys.readouterr().out.lower()


def test_a_cost_state_row_for_an_unpriced_model_is_not_double_reported(
    transcripts, rates_file, capsys
):
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-future-9": {
            "inputTokens": 100, "outputTokens": 10, "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0, "webSearchRequests": 0, "costUSD": 1.0}})],
    )

    code = cmr.main(["--transcripts", str(transcripts), "--rates", str(rates_file({}))])

    assert code == 1
    assert capsys.readouterr().out.count("claude-future-9") == 1


def test_a_zero_cost_row_is_ignored(transcripts, rates_file):
    # Claude Code writes cost-state records before any billed call happens.
    _write(
        transcripts / "p" / "s.jsonl",
        [_cost_state_line({"claude-opus-5": {
            "inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0, "webSearchRequests": 0, "costUSD": 0}})],
    )

    assert cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-opus-5": OPUS_5}))]
    ) == 0


def test_an_absent_transcript_root_is_not_a_failure(tmp_path, rates_file, capsys):
    code = cmr.main(
        ["--transcripts", str(tmp_path / "nope"), "--rates", str(rates_file({}))]
    )

    assert code == 0
    assert "no transcripts" in capsys.readouterr().out.lower()


def test_malformed_lines_do_not_stop_the_scan(transcripts, rates_file):
    _write(
        transcripts / "p" / "s.jsonl",
        ["not json {{{", _usage_line("claude-opus-5"), ""],
    )

    assert cmr.main(
        ["--transcripts", str(transcripts), "--rates", str(rates_file({"claude-opus-5": OPUS_5}))]
    ) == 0
