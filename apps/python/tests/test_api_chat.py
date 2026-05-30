"""Tests for /api/chat — SSE streaming Q&A endpoint."""
import io

import pytest

pytestmark = pytest.mark.usefixtures("isolated_state")


@pytest.fixture
def briefing_setup(tmp_path, monkeypatch):
    """Create a briefing dir + briefing file. Re-points the router's
    location constants so the test owns the filesystem."""
    briefing_dir = tmp_path / "output" / "briefing"
    briefing_dir.mkdir(parents=True)
    briefing_file = briefing_dir / "briefing_2026-05-30.md"
    briefing_file.write_text("== test briefing ==")
    sessions_dir = briefing_dir / ".sessions"
    sessions_dir.mkdir()

    monkeypatch.setattr("web.routers.chat.BRIEFING_DIR", briefing_dir)
    monkeypatch.setattr("web.routers.chat.SESSIONS_DIR", sessions_dir)
    return briefing_dir


class FakePopen:
    """Stand-in for subprocess.Popen for the chat router tests.

    Yields the given stdout_lines from ``proc.stdout`` and exposes the given
    stderr/returncode after ``wait()``.
    """

    def __init__(
        self,
        cmd,
        stdout_lines: list[bytes] | None = None,
        stderr: bytes = b"",
        returncode: int = 0,
        **kwargs,
    ):
        self.cmd = cmd
        self.kwargs = kwargs
        self.stdout = iter(stdout_lines or [])
        self.stderr = io.BytesIO(stderr)
        self._returncode = returncode
        self.returncode = None

    def wait(self):
        self.returncode = self._returncode
        return self._returncode


def _make_popen(stdout_lines=None, stderr=b"", returncode=0):
    """Return a factory closure suitable for monkeypatching subprocess.Popen.

    Records every invocation in ``calls`` for assertions."""
    calls = []

    def factory(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakePopen(cmd, stdout_lines=stdout_lines, stderr=stderr, returncode=returncode)

    factory.calls = calls
    return factory


async def test_chat_returns_sse_content_type(authed_client, briefing_setup, monkeypatch):
    factory = _make_popen(stdout_lines=[b"hello\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "What's up?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


async def test_chat_streams_stdout_lines_as_data_events(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen(stdout_lines=[b"line1\n", b"line2\n", b"line3\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    body = response.text

    assert "data: line1\n\n" in body
    assert "data: line2\n\n" in body
    assert "data: line3\n\n" in body


async def test_chat_first_request_creates_new_session_with_briefing_context(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )

    assert len(factory.calls) == 1
    cmd, _kwargs = factory.calls[0]
    assert "--session-id" in cmd
    assert "--append-system-prompt" in cmd
    prompt_idx = cmd.index("--append-system-prompt") + 1
    assert "== test briefing ==" in cmd[prompt_idx]
    assert "-p" in cmd
    assert cmd[cmd.index("-p") + 1] == "Q?"

    session_file = briefing_setup / ".sessions" / "2026-05-30"
    assert session_file.exists()


async def test_chat_resume_uses_saved_session_id(
    authed_client, briefing_setup, monkeypatch
):
    session_file = briefing_setup / ".sessions" / "2026-05-30"
    session_file.write_text("saved-uuid-xyz")

    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )

    cmd, _ = factory.calls[0]
    assert "--resume" in cmd
    assert "saved-uuid-xyz" in cmd
    assert "--append-system-prompt" not in cmd


async def test_chat_stale_session_deletes_file_and_emits_event(
    authed_client, briefing_setup, monkeypatch
):
    session_file = briefing_setup / ".sessions" / "2026-05-30"
    session_file.write_text("stale-uuid")

    factory = _make_popen(
        stderr=b"No conversation found with session ID: stale-uuid\n",
        returncode=1,
    )
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )

    assert response.status_code == 200
    assert "event: stale_session" in response.text
    assert not session_file.exists()


async def test_chat_other_subprocess_error_emits_error_event(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen(stderr=b"auth failed", returncode=1)
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "auth failed" in response.text


async def test_chat_404_when_briefing_missing(authed_client, briefing_setup):
    response = await authed_client.post(
        "/api/chat",
        json={"date": "2099-12-31", "question": "Q?"},
    )
    assert response.status_code == 404


async def test_chat_subprocess_env_strips_anthropic_api_key_in_cli_mode(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-be-stripped")

    await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )

    _, kwargs = factory.calls[0]
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]


async def test_chat_requires_bearer(async_client, briefing_setup):
    response = await async_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    assert response.status_code == 401
