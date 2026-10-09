"""Tests for POST /api/archive — runs archive.sh via subprocess.

The subprocess call is patched so these tests stay fast and host-independent.
"""
import subprocess

from web.routers import archive as archive_router


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
