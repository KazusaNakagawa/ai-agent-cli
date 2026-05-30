"""Tests for src/state.py — ~/.ai-agent/state.json persistence."""
import json

import pytest

from src import state as state_mod


@pytest.fixture(autouse=True)
def isolated_state_file(monkeypatch, tmp_path):
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")


def test_read_returns_defaults_when_no_file():
    s = state_mod.read_state()
    assert s.onboarded is False
    assert s.auth_mode == "cli"
    assert s.migrated_from_env is False
    assert s.version == 1


def test_write_and_read_roundtrip():
    state_mod.write_state(
        state_mod.State(onboarded=True, auth_mode="api", migrated_from_env=True),
    )
    s = state_mod.read_state()
    assert s.onboarded is True
    assert s.auth_mode == "api"
    assert s.migrated_from_env is True


def test_write_rejects_invalid_auth_mode():
    with pytest.raises(ValueError, match="auth_mode"):
        state_mod.write_state(
            state_mod.State(onboarded=True, auth_mode="oauth", migrated_from_env=False),
        )


def test_write_creates_parent_dir(monkeypatch, tmp_path):
    nested = tmp_path / "nested" / "state.json"
    monkeypatch.setattr(state_mod, "STATE_FILE", nested)
    state_mod.write_state(state_mod.State())
    assert nested.exists()


def test_read_preserves_unknown_fields_via_version():
    """A state file written by a future version (with extra fields) must still
    deserialize to a sensible State without exploding.
    """
    state_mod.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state_mod.STATE_FILE.write_text(
        json.dumps(
            {
                "onboarded": True,
                "auth_mode": "cli",
                "migrated_from_env": False,
                "version": 2,
                "future_field": "ignored",
            }
        )
    )
    s = state_mod.read_state()
    assert s.onboarded is True
    assert s.version == 2
