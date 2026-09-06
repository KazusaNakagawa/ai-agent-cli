"""Tests for loading the rate table out of config/model_rates.json.

The table used to be a literal in claude_rates.py, which is how claude-opus-5
went unpriced for three weeks with only an amber line in the UI to say so.
These tests pin the file contract so the loader fails loudly instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import claude_rates

RATE_FIELDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")


def _write_rates(path: Path, rates: dict) -> Path:
    path.write_text(json.dumps({"rates": rates}))
    return path


# --- lazy loading ---


def test_the_table_is_not_read_at_import():
    """No module-level RATES assignment — that is what makes loading lazy.

    Eager loading made ``scripts/check_model_rates.py`` — the tool whose whole
    job is to diagnose this file — die during import with a traceback, before
    argparse ran.
    """
    assert "RATES" not in vars(claude_rates)
    assert claude_rates.RATES  # resolved through __getattr__ on first use


def test_a_broken_table_raises_on_use_rather_than_import(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_rates, "RATES_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(claude_rates, "_cached_rates", None)

    with pytest.raises(FileNotFoundError, match="model rate table not found"):
        claude_rates.RATES  # noqa: B018 — attribute access is the trigger


def test_the_table_is_read_once_and_cached(monkeypatch):
    calls = []
    real = claude_rates.load_rates
    monkeypatch.setattr(claude_rates, "_cached_rates", None)
    monkeypatch.setattr(
        claude_rates, "load_rates", lambda p: calls.append(p) or real(p)
    )

    first, second = claude_rates.RATES, claude_rates.RATES

    assert first is second
    assert len(calls) == 1


def test_an_unknown_module_attribute_still_raises_attribute_error():
    with pytest.raises(AttributeError, match="no attribute 'NOPE'"):
        claude_rates.NOPE


# --- success ---


def test_default_config_file_backs_the_module_table():
    loaded = claude_rates.load_rates(claude_rates.RATES_PATH)

    assert loaded == claude_rates.RATES
    assert claude_rates.RATES_PATH.name == "model_rates.json"


def test_every_model_resolves_to_a_five_field_rate_tuple():
    for model, rate in claude_rates.RATES.items():
        assert len(rate) == 5, model
        assert all(isinstance(v, float) for v in rate), model


def test_rates_load_in_declared_field_order(tmp_path):
    path = _write_rates(
        tmp_path / "r.json",
        {
            "m": {
                "input": 1.0,
                "output": 2.0,
                "cache_write_5m": 3.0,
                "cache_write_1h": 4.0,
                "cache_read": 5.0,
            }
        },
    )

    assert claude_rates.load_rates(path) == {"m": (1.0, 2.0, 3.0, 4.0, 5.0)}


def test_cache_multipliers_hold_for_every_model_without_published_overrides():
    # 5-minute write is 1.25x input and 1-hour write is 2x input on every
    # current model; only claude-fable-5-1 publishes a non-standard cache read.
    for model, (inp, _, cw5m, cw1h, cr) in claude_rates.RATES.items():
        assert cw5m == pytest.approx(inp * 1.25), model
        assert cw1h == pytest.approx(inp * 2.0), model
        if model != "claude-fable-5-1":
            assert cr == pytest.approx(inp * 0.1), model


# --- failure ---


def test_missing_file_names_the_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="model_rates.json"):
        claude_rates.load_rates(tmp_path / "model_rates.json")


def test_malformed_json_is_reported_as_a_config_error(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{not json")

    with pytest.raises(ValueError, match="not valid JSON"):
        claude_rates.load_rates(path)


def test_missing_rates_key_is_rejected(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"_comment": "no rates here"}))

    with pytest.raises(ValueError, match="rates"):
        claude_rates.load_rates(path)


@pytest.mark.parametrize("dropped", RATE_FIELDS)
def test_a_model_missing_any_rate_field_is_rejected(tmp_path, dropped):
    full = dict.fromkeys(RATE_FIELDS, 1.0)
    del full[dropped]
    path = _write_rates(tmp_path / "r.json", {"claude-x": full})

    with pytest.raises(ValueError, match=dropped):
        claude_rates.load_rates(path)


def test_a_non_numeric_rate_is_rejected(tmp_path):
    path = _write_rates(
        tmp_path / "r.json", {"claude-x": dict.fromkeys(RATE_FIELDS, "free")}
    )

    with pytest.raises(ValueError, match="claude-x"):
        claude_rates.load_rates(path)


# --- boundary ---


def test_an_empty_rate_table_loads_rather_than_erroring(tmp_path):
    # Nothing priced is a legitimate state for a fixture; the checker, not the
    # loader, is what decides an empty table is wrong for a real run.
    assert claude_rates.load_rates(_write_rates(tmp_path / "r.json", {})) == {}


def test_a_zero_rate_is_accepted(tmp_path):
    path = _write_rates(tmp_path / "r.json", {"free": dict.fromkeys(RATE_FIELDS, 0.0)})

    assert claude_rates.load_rates(path) == {"free": (0.0, 0.0, 0.0, 0.0, 0.0)}


def test_a_negative_rate_is_rejected(tmp_path):
    path = _write_rates(
        tmp_path / "r.json", {"claude-x": dict.fromkeys(RATE_FIELDS, -1.0)}
    )

    with pytest.raises(ValueError, match="negative"):
        claude_rates.load_rates(path)


def test_integers_in_the_file_load_as_floats(tmp_path):
    path = _write_rates(tmp_path / "r.json", {"m": dict.fromkeys(RATE_FIELDS, 3)})

    assert claude_rates.load_rates(path) == {"m": (3.0,) * 5}
