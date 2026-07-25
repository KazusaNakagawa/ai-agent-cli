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
import json

import pytest

from src import chat_job_store, journal_store

pytestmark = pytest.mark.usefixtures("isolated_state")


def _delta_line(text: str) -> bytes:
    return (
        json.dumps(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": text},
                },
            }
        )
        + "\n"
    ).encode("utf-8")


def _result_line(*, usage: dict | None = None, result: str = "") -> bytes:
    rec: dict = {"type": "result", "subtype": "success", "result": result}
    if usage is not None:
        rec["usage"] = usage
    return (json.dumps(rec) + "\n").encode("utf-8")


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


async def test_context_capped_at_max_chars(authed_client, journal_dir, monkeypatch):
    # Make each day large and set a small cap so only the newest fits.
    (journal_dir / "2026-06-23.md").write_text("A" * 5000, encoding="utf-8")
    (journal_dir / "2026-06-24.md").write_text("B" * 5000, encoding="utf-8")
    monkeypatch.setattr("web.routers.chat.JOURNAL_CONTEXT_MAX_CHARS", 6000)
    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post("/api/journal/chat", json={"question": "q"})
    assert response.status_code == 202

    cmd = factory.calls[0][0]
    context = cmd[cmd.index("--append-system-prompt") + 1]
    # Newest day kept, older dropped once the budget is exhausted.
    assert "B" * 5000 in context
    assert "A" * 5000 not in context


async def test_stream_reuses_chat_endpoint(authed_client, journal_dir, monkeypatch):
    factory = _make_popen(
        stdout_lines=[_delta_line("Brainstorm idea"), _result_line()]
    )
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    post = await authed_client.post("/api/journal/chat", json={"question": "q"})
    job_id = post.json()["job_id"]
    stream = await authed_client.get(f"/api/chat/{job_id}/stream")
    assert stream.status_code == 200
    assert "Brainstorm idea" in stream.text


async def test_journal_logs_usage_with_journal_label(
    authed_client, journal_dir, monkeypatch
):
    """A journal brainstorm turn records a usage-log entry labeled ``journal``."""
    captured: list[dict] = []
    monkeypatch.setattr(
        "web.routers.chat.log_usage", lambda **kw: captured.append(kw)
    )
    usage = {"input_tokens": 7, "output_tokens": 11}
    factory = _make_popen(
        stdout_lines=[_delta_line("an idea"), _result_line(usage=usage)]
    )
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    post = await authed_client.post("/api/journal/chat", json={"question": "q"})
    job_id = post.json()["job_id"]
    stream = await authed_client.get(f"/api/chat/{job_id}/stream")

    # Verify streaming still delivers assistant text even when usage logging is active.
    assert "an idea" in stream.text
    assert len(captured) == 1
    assert captured[0]["label"] == "journal"
    assert captured[0]["usage"]["output_tokens"] == 11


def test_gather_context_is_day_based(tmp_path, monkeypatch):
    """`days` caps by distinct dates; multiple entries on a day all load."""
    from web.routers.chat import _gather_journal_context

    d = tmp_path / "journal"
    d.mkdir()
    # Two entries on the newest date, one each on the two older dates.
    (d / "2026-06-24_090000.md").write_text("note A", encoding="utf-8")
    (d / "2026-06-24_100000.md").write_text("note B", encoding="utf-8")
    (d / "2026-06-23_090000.md").write_text("note C", encoding="utf-8")
    (d / "2026-06-22_090000.md").write_text("note D", encoding="utf-8")
    monkeypatch.setattr(journal_store, "JOURNAL_DIR", d)

    # days=2 → newest two dates (06-24, 06-23): both 06-24 entries + the 06-23 one.
    blob = _gather_journal_context(days=2)
    assert "note A" in blob and "note B" in blob and "note C" in blob
    assert "note D" not in blob


class TestJournalChatTrustedWriteDirs:
    """#414: configured trusted_write_dirs flow into the claude CLI invocation
    so Journal chat can actually save to a known directory instead of being
    silently denied."""

    async def test_configured_dirs_add_permission_flags(
        self, authed_client, journal_dir, monkeypatch, tmp_path
    ):
        trusted_dir = str(tmp_path / "zenn-docs")
        monkeypatch.setattr(
            "web.routers.chat.config.get_journal_chat_trusted_write_dirs",
            lambda: [trusted_dir],
        )
        factory = _make_popen()
        monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

        response = await authed_client.post("/api/journal/chat", json={"question": "q"})
        assert response.status_code == 202

        cmd = factory.calls[0][0]
        assert "--permission-mode" in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
        assert "--add-dir" in cmd
        assert cmd[cmd.index("--add-dir") + 1] == trusted_dir

    async def test_no_configured_dirs_omits_permission_flags(
        self, authed_client, journal_dir, monkeypatch
    ):
        monkeypatch.setattr(
            "web.routers.chat.config.get_journal_chat_trusted_write_dirs",
            lambda: [],
        )
        factory = _make_popen()
        monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

        response = await authed_client.post("/api/journal/chat", json={"question": "q"})
        assert response.status_code == 202

        cmd = factory.calls[0][0]
        assert "--add-dir" not in cmd
        assert "--permission-mode" not in cmd


class TestJournalChatVision:
    async def test_journal_chat_rejects_traversal_image_path(self, authed_client, journal_dir):
        """image_path outside IMAGES_ROOT is rejected with 400."""
        resp = await authed_client.post(
            "/api/journal/chat",
            json={"question": "Q", "image_path": "/etc/passwd"},
        )
        assert resp.status_code == 400
        assert "Invalid image path" in resp.json()["detail"]
