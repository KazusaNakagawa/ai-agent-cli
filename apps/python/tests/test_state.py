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


def test_read_rejects_invalid_auth_mode_on_disk():
    """A hand-edited or downgrade-corrupted state.json with an unknown
    auth_mode must fail loudly instead of silently degrading to cli."""
    state_mod.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state_mod.STATE_FILE.write_text(
        json.dumps({"onboarded": True, "auth_mode": "oauth", "migrated_from_env": False, "version": 1})
    )
    with pytest.raises(ValueError, match="auth_mode"):
        state_mod.read_state()


def test_write_is_atomic_leaves_no_tmp_on_failure(monkeypatch):
    """If os.replace fails mid-write, neither the tempfile nor a truncated
    state.json should remain."""

    def _boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr(state_mod.os, "replace", _boom)

    with pytest.raises(OSError):
        state_mod.write_state(state_mod.State(auth_mode="api"))

    leftover = [
        p for p in state_mod.STATE_FILE.parent.iterdir() if p.suffix == ".tmp"
    ]
    assert leftover == [], f"tmp file not cleaned up: {leftover}"
    assert not state_mod.STATE_FILE.exists()
