"""Tests for /api/journal/chat — journaling brainstorm chat (#271, Phase 2).

Contract:
- ``POST /api/journal/chat`` returns ``202 {job_id, status}`` and schedules
  the claude subprocess, seeded with recent journal entries as context.
- 404 when there are no journal entries to brainstorm over.
- The job streams via the shared ``GET /api/chat/{job_id}/stream``.
- Auth (Bearer) is required.

Mirrors test_api_chat.py: in test mode the BackgroundTask runs
synchronously, so the FakePopen has completed by the time POST returns.
"""
import io

import pytest

from src import chat_job_store, journal_store

pytestmark = pytest.mark.usefixtures("isolated_state")


@pytest.fixture(autouse=True)
def reset_chat_store():
    chat_job_store._reset_for_tests()
    yield
    chat_job_store._reset_for_tests()


@pytest.fixture
def journal_dir(tmp_path, monkeypatch):
    """Point the journal store at a tmp dir with two days of entries."""
    d = tmp_path / "journal"
    d.mkdir()
    (d / "2026-06-23.md").write_text("# Journal 2026-06-23\n\nDay one note.", encoding="utf-8")
    (d / "2026-06-24.md").write_text("# Journal 2026-06-24\n\nDay two note.", encoding="utf-8")
    monkeypatch.setattr(journal_store, "JOURNAL_DIR", d)
    return d


class FakePopen:
    def __init__(self, cmd, stdout_lines=None, stderr=b"", returncode=0, **kwargs):
        self.cmd = cmd
        self.stdout = iter(stdout_lines or [])
        self.stderr = io.BytesIO(stderr)
        self._returncode = returncode
        self.returncode = None

    def wait(self):
        self.returncode = self._returncode
        return self._returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        pass


def _make_popen(stdout_lines=None):
    calls = []

    def factory(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakePopen(cmd, stdout_lines=stdout_lines)

    factory.calls = calls
    return factory


async def test_post_requires_auth(async_client, journal_dir):
    response = await async_client.post("/api/journal/chat", json={"question": "ideas?"})
    assert response.status_code == 401


async def test_post_returns_202_with_job_id(authed_client, journal_dir, monkeypatch):
    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post("/api/journal/chat", json={"question": "ideas?"})

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"]
    assert chat_job_store.get_job(body["job_id"]) is not None


async def test_post_404_when_no_entries(authed_client, tmp_path, monkeypatch):
    monkeypatch.setattr(journal_store, "JOURNAL_DIR", tmp_path / "empty")
    response = await authed_client.post("/api/journal/chat", json={"question": "ideas?"})
    assert response.status_code == 404


async def test_post_rejects_empty_question(authed_client, journal_dir):
    response = await authed_client.post("/api/journal/chat", json={"question": ""})
    assert response.status_code == 422


async def test_post_rejects_out_of_range_days(authed_client, journal_dir):
    for bad in (0, 32):
        response = await authed_client.post(
            "/api/journal/chat", json={"question": "q", "days": bad}
        )
        assert response.status_code == 422, f"expected 422 for days={bad}"


async def test_context_includes_recent_entries(authed_client, journal_dir, monkeypatch):
    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post("/api/journal/chat", json={"question": "q"})
    assert response.status_code == 202

    # The first (new-session) invocation carries the journal context in the
    # --append-system-prompt argument.
    cmd = factory.calls[0][0]
    assert "--append-system-prompt" in cmd
    context = cmd[cmd.index("--append-system-prompt") + 1]
    assert "Day one note." in context
    assert "Day two note." in context


async def test_days_limits_context(authed_client, journal_dir, monkeypatch):
    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/journal/chat", json={"question": "q", "days": 1}
    )
    assert response.status_code == 202

    cmd = factory.calls[0][0]
    context = cmd[cmd.index("--append-system-prompt") + 1]
    # Only the newest day (2026-06-24) is loaded.
    assert "Day two note." in context
    assert "Day one note." not in context


async def test_stream_reuses_chat_endpoint(authed_client, journal_dir, monkeypatch):
    factory = _make_popen(stdout_lines=[b"Brainstorm idea\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    post = await authed_client.post("/api/journal/chat", json={"question": "q"})
    job_id = post.json()["job_id"]
    stream = await authed_client.get(f"/api/chat/{job_id}/stream")
    assert stream.status_code == 200
    assert "Brainstorm idea" in stream.text
