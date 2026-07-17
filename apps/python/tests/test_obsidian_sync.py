"""Tests for journal -> Obsidian vault one-way sync.

Contract:
- ``sync_entry`` writes the entry's full content to
  ``<vault>/<journal_subdir>/<entry_id>.md`` (overwrite, not append).
- Missing vault dir or missing entry logs and returns without raising.
"""
from unittest.mock import patch

from src.notifier import obsidian_sync


def test_sync_entry_writes_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="# Note\nbody"):
        obsidian_sync.sync_entry("2026-07-17_120000", vault, "journal")
    dest = vault / "journal" / "2026-07-17_120000.md"
    assert dest.read_text(encoding="utf-8") == "# Note\nbody"


def test_sync_entry_overwrites_on_resync(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="v1"):
        obsidian_sync.sync_entry("2026-07-17_120000", vault, "journal")
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="v1\nv2"):
        obsidian_sync.sync_entry("2026-07-17_120000", vault, "journal")
    dest = vault / "journal" / "2026-07-17_120000.md"
    assert dest.read_text(encoding="utf-8") == "v1\nv2"


def test_sync_entry_noop_when_vault_missing(tmp_path):
    missing = tmp_path / "no-such-vault"
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="body"):
        obsidian_sync.sync_entry("2026-07-17_120000", missing, "journal")  # must not raise
    assert not missing.exists()


def test_sync_entry_noop_when_entry_missing(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value=None):
        obsidian_sync.sync_entry("2026-07-17_999999", vault, "journal")  # must not raise
    assert not (vault / "journal").exists()
