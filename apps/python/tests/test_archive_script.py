"""Tests for apps/python/bin/archive.sh — target-file selection and rclone errors.

The script is exercised as a subprocess with ``ARCHIVE_*`` env overrides and a
fake ``rclone`` on PATH so no network or real Drive remote is needed.
"""
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

ARCHIVE_SCRIPT = Path(__file__).parents[1] / "bin" / "archive.sh"


def _seed_briefings(briefing_dir: Path) -> None:
    briefing_dir.mkdir(parents=True, exist_ok=True)
    # Two months plus a non-md file that must never be archived.
    (briefing_dir / "briefing_2026-05-01.md").write_text("may 1", encoding="utf-8")
    (briefing_dir / "local_2026-05-15.md").write_text("may 15", encoding="utf-8")
    (briefing_dir / "briefing_2026-06-01.md").write_text("june 1", encoding="utf-8")
    (briefing_dir / "notes.txt").write_text("ignore", encoding="utf-8")


def _fake_rclone(bin_dir: Path) -> None:
    """A stub rclone that always succeeds, shadowing any real install."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "rclone"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)


def _run(tmp_path, *args, env_extra=None):
    env = os.environ.copy()
    env["ARCHIVE_BRIEFING_DIR"] = str(tmp_path / "briefing")
    env["ARCHIVE_OUTPUT_DIR"] = str(tmp_path / "archive")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["/bin/bash", str(ARCHIVE_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_archives_only_target_month(tmp_path):
    _seed_briefings(tmp_path / "briefing")
    fake_bin = tmp_path / "bin"
    _fake_rclone(fake_bin)

    result = _run(
        tmp_path, "--month", "2026-05",
        env_extra={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr

    zip_path = tmp_path / "archive" / "briefing_2026-05.zip"
    assert zip_path.exists()
    names = sorted(zipfile.ZipFile(zip_path).namelist())
    # Only May md files, not June and not the .txt.
    assert names == ["briefing_2026-05-01.md", "local_2026-05-15.md"]


def test_no_files_skips_with_zero_exit(tmp_path):
    _seed_briefings(tmp_path / "briefing")
    fake_bin = tmp_path / "bin"
    _fake_rclone(fake_bin)

    result = _run(
        tmp_path, "--month", "2026-01",
        env_extra={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0
    assert "skip" in result.stdout.lower()
    assert not (tmp_path / "archive" / "briefing_2026-01.zip").exists()


def test_local_md_retained_by_default(tmp_path):
    _seed_briefings(tmp_path / "briefing")
    fake_bin = tmp_path / "bin"
    _fake_rclone(fake_bin)

    _run(tmp_path, "--month", "2026-05", env_extra={"PATH": f"{fake_bin}:{os.environ['PATH']}"})
    assert (tmp_path / "briefing" / "briefing_2026-05-01.md").exists()


def test_prune_removes_local_md(tmp_path):
    _seed_briefings(tmp_path / "briefing")
    fake_bin = tmp_path / "bin"
    _fake_rclone(fake_bin)

    _run(
        tmp_path, "--month", "2026-05", "--prune",
        env_extra={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert not (tmp_path / "briefing" / "briefing_2026-05-01.md").exists()
    assert not (tmp_path / "briefing" / "local_2026-05-15.md").exists()
    # June file untouched.
    assert (tmp_path / "briefing" / "briefing_2026-06-01.md").exists()


def test_missing_rclone_exits_nonzero_with_hint(tmp_path):
    _seed_briefings(tmp_path / "briefing")
    # Minimal PATH with only the externals the script needs before the rclone
    # check (dirname), so rclone is genuinely absent regardless of the host.
    minimal_bin = tmp_path / "minbin"
    minimal_bin.mkdir()
    (minimal_bin / "dirname").symlink_to("/usr/bin/dirname")

    result = _run(
        tmp_path, "--month", "2026-05",
        env_extra={"PATH": str(minimal_bin)},
    )
    assert result.returncode == 1
    assert "rclone not found" in result.stderr.lower()


def test_unsupported_date_without_month_exits_with_hint(tmp_path):
    _seed_briefings(tmp_path / "briefing")
    # Stub `date` that fails for every form, simulating a minimal/BusyBox host,
    # and omit --month so the default-month branch is exercised.
    stub_bin = tmp_path / "stubbin"
    stub_bin.mkdir()
    (stub_bin / "dirname").symlink_to("/usr/bin/dirname")
    date_stub = stub_bin / "date"
    date_stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    date_stub.chmod(0o755)

    result = _run(tmp_path, env_extra={"PATH": str(stub_bin)})
    assert result.returncode == 1
    assert "supply --month" in result.stderr.lower()
