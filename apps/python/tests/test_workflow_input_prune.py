"""Tests for the input-prune workflow (#605)."""
from datetime import datetime

from src.workflow.runner import run_workflow


def test_input_prune_deletes_old_unreferenced_uploads(tmp_path, monkeypatch):
    from src import paths
    from src.workflow.definitions.input_prune import INPUT_PRUNE

    input_dir, output_dir = tmp_path / "input", tmp_path / "output"
    old = input_dir / "images" / "2020-01-01" / "a.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    output_dir.mkdir()
    monkeypatch.setattr(paths, "INPUT_DIR", input_dir)
    monkeypatch.setattr(paths, "OUTPUT_DIR", output_dir)

    record = run_workflow(INPUT_PRUNE)

    assert record.status == "done"
    assert not old.exists()
    assert record.results["prune"] == [str(old)]


def test_input_prune_uses_the_money_ledger_import_log(tmp_path, monkeypatch):
    """The workflow must read the same log `money import` writes."""
    from src import input_retention, paths
    from src.money.importer import import_log_path
    from src.money.models import STORE_PATH
    from src.workflow.definitions.input_prune import INPUT_PRUNE

    seen = {}

    def fake_prune(**kwargs):
        seen.update(kwargs)
        return input_retention.PruneResult()

    monkeypatch.setattr(input_retention, "prune", fake_prune)
    monkeypatch.setattr(paths, "INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(paths, "OUTPUT_DIR", tmp_path / "output")
    run_workflow(INPUT_PRUNE)

    assert seen["import_log"] == import_log_path(STORE_PATH)
    assert seen["dry_run"] is False
    assert isinstance(seen["now"], datetime)
