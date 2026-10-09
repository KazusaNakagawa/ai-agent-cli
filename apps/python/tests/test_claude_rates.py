"""Tests for the per-model rate table in src.claude_rates.

Rates mirror the published Anthropic pricing doc
(https://platform.claude.com/docs/en/about-claude/pricing.md).
"""
import json
import logging

import pytest

from src import claude_rates, usage_monitor
from src.claude_rates import RATES, rate_for, usage_cost


@pytest.fixture(autouse=True)
def _reset_warnings():
    claude_rates.reset_unpriced_warnings()
    yield
    claude_rates.reset_unpriced_warnings()


# --- success ---


@pytest.mark.parametrize(
    "model, expected",
    [
        # (input, output, cache_write_5m, cache_write_1h, cache_read)
        ("claude-opus-5-5", (4.00, 20.00, 5.00, 8.00, 0.20)),
        ("claude-sonnet-5-5", (2.00, 10.00, 2.50, 4.00, 0.10)),
    ],
)
def test_claude_5_5_models_are_priced(model, expected, caplog):
    with caplog.at_level(logging.WARNING, logger="src.claude_rates"):
        assert rate_for(model) == expected
    assert "no rate table entry" not in caplog.text


def test_opus_5_5_cache_read_is_5_percent_of_input():
    # Opus/Sonnet 5.5 publish their own cache-hit multiplier (0.05x, not 0.1x).
    for model in ("claude-opus-5-5", "claude-sonnet-5-5"):
        in_rate, _, _, _, cr_rate = RATES[model]
        assert cr_rate == pytest.approx(in_rate * 0.05)


def test_aggregate_costs_opus_5_5_and_reports_nothing_unpriced(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "s.jsonl").write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-10-09T03:00:00.000Z",
                "message": {
                    "id": "m1",
                    "model": "claude-opus-5-5",
                    "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
                },
            }
        )
        + "\n"
    )
    report = usage_monitor.aggregate(tmp_path)
    assert report.by_model["claude-opus-5-5"].cost == pytest.approx(4.00 + 20.00)
    assert report.unpriced_models == set()


# --- failure ---


def test_unknown_model_still_costs_zero_and_is_reported(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "s.jsonl").write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-10-09T03:00:00.000Z",
                "message": {
                    "id": "m1",
                    "model": "claude-future-9",
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            }
        )
        + "\n"
    )
    report = usage_monitor.aggregate(tmp_path)
    assert report.by_model["claude-future-9"].cost == 0
    assert report.unpriced_models == {"claude-future-9"}


# --- boundary ---


def test_synthetic_pseudo_model_is_not_reported_as_unpriced(tmp_path):
    # Claude Code writes zero-usage "<synthetic>" messages; they are not a
    # real model and must not trip the unpriced warning.
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "s.jsonl").write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-10-09T03:00:00.000Z",
                "message": {
                    "id": "m1",
                    "model": "<synthetic>",
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            }
        )
        + "\n"
    )
    report = usage_monitor.aggregate(tmp_path)
    assert report.unpriced_models == set()


def test_zero_usage_costs_zero_for_priced_model():
    assert usage_cost({}, "claude-opus-5-5") == 0
