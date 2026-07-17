"""Tests for src/notion_comment_state.py — ingested Notion comment ID tracking (#396)."""
import json

import pytest

from src import notion_comment_state as state_mod


@pytest.fixture(autouse=True)
def isolated_state_file(monkeypatch, tmp_path):
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "ingested_notion_comments.json")


def test_read_returns_empty_set_when_no_file():
    assert state_mod.read_seen_ids() == set()


def test_write_and_read_roundtrip():
    state_mod.write_seen_ids({"c1", "c2"})
    assert state_mod.read_seen_ids() == {"c1", "c2"}


def test_write_creates_parent_dir(monkeypatch, tmp_path):
    nested = tmp_path / "nested" / "ingested_notion_comments.json"
    monkeypatch.setattr(state_mod, "STATE_FILE", nested)
    state_mod.write_seen_ids({"c1"})
    assert nested.exists()


def test_read_returns_empty_set_on_malformed_json():
    state_mod.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state_mod.STATE_FILE.write_text("{not json")
    assert state_mod.read_seen_ids() == set()


def test_read_returns_empty_set_when_ids_field_is_wrong_type():
    state_mod.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state_mod.STATE_FILE.write_text(json.dumps({"ids": "not-a-list"}))
    assert state_mod.read_seen_ids() == set()


def test_write_is_atomic_leaves_no_tmp_on_failure(monkeypatch):
    def _boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr(state_mod.os, "replace", _boom)

    with pytest.raises(OSError):
        state_mod.write_seen_ids({"c1"})

    leftover = [p for p in state_mod.STATE_FILE.parent.iterdir() if p.suffix == ".tmp"]
    assert leftover == [], f"tmp file not cleaned up: {leftover}"
    assert not state_mod.STATE_FILE.exists()
