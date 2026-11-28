"""Tests for POST /api/archive — runs archive.sh via subprocess.

The subprocess call is patched so these tests stay fast and host-independent.
"""
import subprocess



def _fake_run(returncode=0, stdout="", stderr=""):
    def _run(cmd, capture_output, text, env=None):  # noqa: ANN001 - mirror subprocess.run
        _run.cmd = cmd
        _run.env = env
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    return _run


async def test_archive_requires_auth(async_client):
    response = await async_client.post("/api/archive")
    assert response.status_code == 401


async def test_archive_success_returns_stdout(authed_client, monkeypatch):
    fake = _fake_run(returncode=0, stdout="created: briefing_2026-05.zip\n")
    monkeypatch.setattr(subprocess, "run", fake)

    response = await authed_client.post("/api/archive")
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 0
    assert "briefing_2026-05.zip" in body["stdout"]
    # default invocation has no --month flag
    assert "--month" not in fake.cmd


async def test_archive_passes_month_and_prune(authed_client, monkeypatch):
    fake = _fake_run(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake)

    response = await authed_client.post("/api/archive?month=2026-05&prune=true")
    assert response.status_code == 200
    assert "--month" in fake.cmd and "2026-05" in fake.cmd
    assert "--prune" in fake.cmd


async def test_archive_rejects_bad_month(authed_client):
    response = await authed_client.post("/api/archive?month=2026/05")
    assert response.status_code == 422


async def test_archive_failure_returns_500_with_stderr(authed_client, monkeypatch):
    fake = _fake_run(returncode=1, stderr="error: rclone not found")
    monkeypatch.setattr(subprocess, "run", fake)

    response = await authed_client.post("/api/archive")
    assert response.status_code == 500
    assert "rclone not found" in response.json()["detail"]


async def test_archive_points_the_script_at_the_data_home(authed_client, monkeypatch):
    """archive.sh defaults to repo-relative dirs, so the router passes the
    resolved data-home dirs explicitly (npx installs have no repo)."""
    from src import paths

    fake = _fake_run(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake)

    response = await authed_client.post("/api/archive")
    assert response.status_code == 200
    assert fake.env["ARCHIVE_BRIEFING_DIR"] == str(paths.OUTPUT_DIR / "briefing")
    assert fake.env["ARCHIVE_OUTPUT_DIR"] == str(paths.OUTPUT_DIR / "archive")
    # The rest of the environment (PATH for rclone, etc.) is inherited.
    assert "PATH" in fake.env


# --- structured summary (#591) ---

_ZIP_NOISE = "".join(f"  adding: briefing_2026-10-{day:02d}.md (stored 0%)\n" for day in range(1, 32))


async def test_archive_summarizes_a_successful_run(authed_client, monkeypatch):
    stdout = (
        _ZIP_NOISE
        + "created: /Users/me/out/archive/briefing_2026-10.zip (31 files)\n"
        + "uploaded: gdrive:ai-agent/briefing/briefing_2026-10.zip\n"
    )
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout=stdout))

    body = (await authed_client.post("/api/archive")).json()

    assert body["status"] == "archived"
    assert body["month"] == "2026-10"
    assert body["file_count"] == 31
    assert body["pruned"] is False
    assert body["message"] == "Archived 2026-10 (31 files)"
    # The raw output stays available for debugging, but the message is free of it.
    assert "adding:" in body["stdout"]
    for noise in ("adding:", "deflated", "stored", "/Users/me", "gdrive:"):
        assert noise not in body["message"]


async def test_archive_message_mentions_pruned_copies_and_singular_file(authed_client, monkeypatch):
    stdout = (
        "created: /o/briefing_2026-10.zip (1 files)\n"
        "uploaded: gdrive:a/briefing_2026-10.zip\n"
        "pruned: 1 local md files for 2026-10\n"
    )
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout=stdout))

    body = (await authed_client.post("/api/archive?prune=true")).json()

    assert body["pruned"] is True
    assert body["file_count"] == 1
    assert body["message"] == "Archived 2026-10 (1 file, local copies removed)"


async def test_archive_reports_a_month_with_nothing_to_archive(authed_client, monkeypatch):
    stdout = "skip: no briefing files for 2026-09 in /data/output/briefing\n"
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout=stdout))

    body = (await authed_client.post("/api/archive")).json()

    assert body["status"] == "skipped"
    assert body["month"] == "2026-09"
    assert body["file_count"] == 0
    assert body["message"] == "Nothing to archive for 2026-09: no briefing files."
    assert "/data" not in body["message"]


async def test_archive_falls_back_when_the_output_is_not_recognised(authed_client, monkeypatch):
    """A changed script must not turn a successful run into an error."""
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout="something new\n"))

    response = await authed_client.post("/api/archive")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unknown"
    assert body["month"] is None
    assert body["message"] == "Archive complete."


async def test_archive_ignores_look_alike_lines_inside_zip_noise(authed_client, monkeypatch):
    """Only the script's own ``created:`` line counts, not text inside a file name."""
    stdout = "  adding: created: x/briefing_2026-01.zip (9 files) (stored 0%)\n"
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout=stdout))

    body = (await authed_client.post("/api/archive")).json()

    assert body["status"] == "unknown"


async def test_archive_logs_the_raw_output(authed_client, monkeypatch, caplog):
    stdout = _ZIP_NOISE + "created: /o/briefing_2026-10.zip (31 files)\n"
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=0, stdout=stdout))

    with caplog.at_level("INFO", logger="web.routers.archive"):
        await authed_client.post("/api/archive")

    assert "adding: briefing_2026-10-01.md" in caplog.text
