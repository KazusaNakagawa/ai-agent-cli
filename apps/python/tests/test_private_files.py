import logging
import stat

import pytest

from src import private_files


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_write_private_text_creates_file_0600(tmp_path):
    target = tmp_path / "out" / "report.md"
    private_files.write_private_text(target, "secret body")
    assert target.read_text(encoding="utf-8") == "secret body"
    assert _mode(target) == 0o600


def test_write_private_text_creates_parent_dir_0700(tmp_path):
    target = tmp_path / "out" / "report.md"
    private_files.write_private_text(target, "x")
    assert _mode(target.parent) == 0o700


def test_write_private_text_tightens_existing_loose_file(tmp_path):
    target = tmp_path / "report.md"
    target.write_text("old")
    target.chmod(0o644)
    private_files.write_private_text(target, "new")
    assert target.read_text() == "new"
    assert _mode(target) == 0o600


def test_ensure_private_dir_tightens_existing_dir(tmp_path):
    d = tmp_path / "output"
    d.mkdir()
    d.chmod(0o755)
    private_files.ensure_private_dir(d)
    assert _mode(d) == 0o700


def test_find_loose_paths_flags_group_or_world_access(tmp_path):
    tight = tmp_path / "tight.json"
    tight.write_text("{}")
    tight.chmod(0o600)
    loose = tmp_path / "loose.json"
    loose.write_text("{}")
    loose.chmod(0o644)
    group_only = tmp_path / "group.json"
    group_only.write_text("{}")
    group_only.chmod(0o640)
    missing = tmp_path / "missing.json"
    assert private_files.find_loose_paths([tight, loose, group_only, missing]) == [loose, group_only]


def test_warn_loose_permissions_names_path_not_contents(tmp_path, caplog):
    loose = tmp_path / "holdings.json"
    loose.write_text('{"ticker": "SECRET-CONTENT"}')
    loose.chmod(0o644)
    with caplog.at_level(logging.WARNING, logger=private_files.logger.name):
        found = private_files.warn_loose_permissions([loose])
    assert found == [loose]
    assert str(loose) in caplog.text
    assert "644" in caplog.text
    assert "SECRET-CONTENT" not in caplog.text
    assert _mode(loose) == 0o644, "must warn only, never change silently"


def test_warn_loose_permissions_quiet_when_tight(tmp_path, caplog):
    tight = tmp_path / "ok.json"
    tight.write_text("{}")
    tight.chmod(0o600)
    with caplog.at_level(logging.WARNING, logger=private_files.logger.name):
        assert private_files.warn_loose_permissions([tight]) == []
    assert caplog.text == ""


def test_personal_paths_covers_config_and_data_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(private_files.paths, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(private_files.paths, "INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(private_files.paths, "OUTPUT_DIR", tmp_path / "output")
    names = {p.name for p in private_files.personal_paths()}
    assert {"briefing.json", "holdings.json", "money_rules.json",
            "self_agent_profile.md", "input", "output"} <= names


def test_briefing_md_written_owner_only(tmp_path):
    from datetime import date

    from src.notifier import local_md

    out = tmp_path / "output"
    local_md.save_briefing_md("body", out, 7, today=date(2026, 1, 2), rotation_enabled=False)
    written = out / "briefing_2026-01-02.md"
    assert _mode(written) == 0o600
    assert _mode(out) == 0o700


def test_warn_loose_permissions_survives_path_vanishing_after_check(tmp_path, monkeypatch, caplog):
    loose = tmp_path / "holdings.json"
    loose.write_text("{}")
    loose.chmod(0o644)

    real_stat = type(loose).stat
    calls = {"n": 0}

    def flaky_stat(self, *args, **kwargs):
        if self == loose:
            calls["n"] += 1
            if calls["n"] > 1:
                raise FileNotFoundError(self)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(type(loose), "stat", flaky_stat)
    with caplog.at_level(logging.WARNING, logger=private_files.logger.name):
        found = private_files.warn_loose_permissions([loose])
    assert found == [loose]
    assert calls["n"] == 1, "one stat per path"
    assert str(loose) in caplog.text
