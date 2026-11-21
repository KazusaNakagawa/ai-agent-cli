"""Tests for src/input_retention.py — pruning raw inputs after processing (#605)."""
import json
from datetime import datetime, timedelta

import pytest

from src import input_retention as ir

NOW = datetime(2026, 11, 20, 9, 0, 0)
DAYS = 3


@pytest.fixture
def tree(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    (input_dir / "money").mkdir(parents=True)
    output_dir.mkdir()
    return input_dir, output_dir, output_dir / "money" / "imports.jsonl"


def _csv(input_dir, name="bank_2026-10.csv", text="a,b\n1,2\n"):
    path = input_dir / "money" / name
    path.write_text(text)
    return path


def _prune(tree, *, dry_run=False, now=NOW):
    input_dir, output_dir, log = tree
    return ir.prune(
        input_dir=input_dir,
        output_dir=output_dir,
        import_log=log,
        now=now,
        retention_days=DAYS,
        dry_run=dry_run,
    )


# --- import log ---


def test_record_imports_writes_owner_only_log(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW)
    entry = json.loads(log.read_text().strip())
    assert entry["path"] == str(path.resolve())
    assert entry["parser"] == "rakuten_bank"
    assert entry["imported_at"] == "2026-11-20T09:00:00"
    assert len(entry["sha256"]) == 64
    assert log.stat().st_mode & 0o777 == 0o600


def test_reimport_replaces_the_entry_for_the_same_path(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW - timedelta(days=10))
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW)
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["imported_at"] == "2026-11-20T09:00:00"


# --- statements ---


def test_statement_older_than_window_is_deleted(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW - timedelta(days=DAYS, seconds=1))
    result = _prune(tree)
    assert not path.exists()
    assert result.deleted == [path.resolve()]
    assert log.read_text().strip() == ""  # entry dropped with its file


def test_statement_imported_today_is_kept(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW)
    assert _prune(tree).deleted == []
    assert path.exists()


def test_statement_exactly_at_window_is_kept(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW - timedelta(days=DAYS))
    _prune(tree)
    assert path.exists()


def test_manual_statement_is_never_deleted(tree):
    input_dir, _, log = tree
    path = _csv(input_dir, "mufg_2025-07.csv")
    ir.record_imports(log, [(path, "manual")], now=NOW - timedelta(days=365))
    _prune(tree)
    assert path.exists()


def test_statement_changed_since_import_is_kept(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW - timedelta(days=30))
    path.write_text("a,b\n9,9\n")  # re-downloaded or edited
    _prune(tree)
    assert path.exists()


def test_statement_outside_input_dir_is_never_deleted(tree, tmp_path):
    _, _, log = tree
    elsewhere = tmp_path / "Downloads" / "bank.csv"
    elsewhere.parent.mkdir()
    elsewhere.write_text("x\n")
    ir.record_imports(log, [(elsewhere, "rakuten_bank")], now=NOW - timedelta(days=30))
    _prune(tree)
    assert elsewhere.exists()


def test_missing_statement_drops_its_entry(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW)
    path.unlink()
    assert _prune(tree).deleted == []
    assert log.read_text().strip() == ""


def test_corrupt_log_line_is_skipped(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW - timedelta(days=30))
    log.write_text("not json\n" + log.read_text())
    _prune(tree)
    assert not path.exists()


def test_no_log_and_no_uploads_is_a_noop(tree):
    assert _prune(tree).deleted == []


# --- uploads ---


def _upload(input_dir, kind, day, name):
    path = input_dir / kind / day / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_unreferenced_upload_older_than_window_is_deleted(tree):
    input_dir, _, _ = tree
    old = _upload(input_dir, "images", "2026-11-16", "a.png")
    result = _prune(tree)
    assert not old.exists()
    assert not old.parent.exists()  # empty date dir removed
    assert result.deleted == [old]


def test_upload_within_window_is_kept(tree):
    input_dir, _, _ = tree
    edge = _upload(input_dir, "attachments", "2026-11-17", "b.pdf")  # exactly 3 days
    _prune(tree)
    assert edge.exists()


def test_upload_referenced_from_output_is_kept(tree):
    input_dir, output_dir, _ = tree
    kept = _upload(input_dir, "attachments", "2026-06-28", "c.pdf")
    gone = _upload(input_dir, "attachments", "2026-06-28", "d.pdf")
    journal = output_dir / "journal" / "2026-06-28_120000.md"
    journal.parent.mkdir()
    journal.write_text("see [c.pdf](/api/attachments/2026-06-28/c.pdf)\n")
    _prune(tree)
    assert kept.exists()
    assert not gone.exists()
    assert kept.parent.exists()


def test_non_date_upload_dirs_are_ignored(tree):
    input_dir, _, _ = tree
    odd = _upload(input_dir, "images", "misc", "e.png")
    _prune(tree)
    assert odd.exists()


# --- dry run ---


def test_dry_run_lists_but_deletes_nothing(tree):
    input_dir, _, log = tree
    path = _csv(input_dir)
    ir.record_imports(log, [(path, "rakuten_bank")], now=NOW - timedelta(days=30))
    old = _upload(input_dir, "images", "2026-01-01", "f.png")
    before = log.read_text()
    result = _prune(tree, dry_run=True)
    assert set(result.deleted) == {path.resolve(), old}
    assert path.exists() and old.exists()
    assert log.read_text() == before
