"""Tests for /api/chat — SSE streaming Q&A endpoint."""
import io

import pytest

from src import credentials, state as state_mod

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


async def test_chat_subprocess_env_includes_keychain_key_in_api_mode(
    authed_client, briefing_setup, monkeypatch
):
    state_mod.write_state(state_mod.State(auth_mode="api"))

    store = {("ai-agent", "ANTHROPIC_API_KEY"): "from-keychain"}

    class _Fake:
        def get_password(self, service, name):
            return store.get((service, name))

        def set_password(self, service, name, value):
            store[(service, name)] = value

        def delete_password(self, service, name):
            store.pop((service, name), None)

    monkeypatch.setattr(credentials, "_backend", _Fake())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )

    _, kwargs = factory.calls[0]
    assert kwargs["env"].get("ANTHROPIC_API_KEY") == "from-keychain"


async def test_chat_rejects_invalid_date_format(authed_client, briefing_setup):
    """Path-traversal guard: anything that doesn't match YYYY-MM-DD must 422
    before reaching the filesystem."""
    bad_dates = ["../foo", "2026-05", "2026-5-30", "2026-05-30/extra", "abcd-ef-gh"]
    for bad in bad_dates:
        response = await authed_client.post(
            "/api/chat",
            json={"date": bad, "question": "Q?"},
        )
        assert response.status_code == 422, f"expected 422 for date={bad!r}"


async def test_chat_rejects_empty_question(authed_client, briefing_setup):
    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": ""},
    )
    assert response.status_code == 422


async def test_chat_strips_trailing_cr_from_stdout_lines(
    authed_client, briefing_setup, monkeypatch
):
    """Windows-style \\r\\n line endings must not leak into the SSE event."""
    factory = _make_popen(stdout_lines=[b"hello world\r\n", b"line2\r\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    body = response.text
    # No raw \r before the \n\n event terminator
    assert "\r\n\n" not in body
    assert "data: hello world\n\n" in body
    assert "data: line2\n\n" in body


async def test_chat_multi_line_stderr_emits_one_data_per_line(
    authed_client, briefing_setup, monkeypatch
):
    """Per SSE spec, an event with multi-line content needs one `data:` prefix
    per line — a single `data:` with embedded \\n breaks compliant parsers."""
    factory = _make_popen(stderr=b"err line 1\nerr line 2\nerr line 3", returncode=1)
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    body = response.text
    assert "event: error\n" in body
    assert "data: err line 1\n" in body
    assert "data: err line 2\n" in body
    assert "data: err line 3\n" in body


async def test_chat_requires_bearer(async_client, briefing_setup):
    response = await async_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/chat/notion-import
# ---------------------------------------------------------------------------


def _seed_notion_creds(monkeypatch):
    """Drop NOTION_* into the in-memory keychain so the endpoint short-circuit
    doesn't trip. Requires the ``isolated_keyring`` fixture to be active."""
    from src import credentials as cred_mod
    cred_mod.set_credential("NOTION_API_KEY", "k-test")
    cred_mod.set_credential("NOTION_DATABASE_ID", "db-test")


async def test_chat_notion_import_400_when_both_credentials_missing(
    authed_client, isolated_keyring, clear_credential_env
):
    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "NOTION_API_KEY" in detail
    assert "NOTION_DATABASE_ID" in detail


async def test_chat_notion_import_400_when_api_key_missing(
    authed_client, isolated_keyring, clear_credential_env
):
    from src import credentials as cred_mod
    cred_mod.set_credential("NOTION_DATABASE_ID", "db-test")

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "NOTION_API_KEY" in detail
    assert "NOTION_DATABASE_ID" not in detail


async def test_chat_notion_import_success_appends_to_existing_briefing_page(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds(monkeypatch)
    captured: dict = {}

    def fake_find(api_key, database_id, briefing_date):
        captured["find"] = (api_key, database_id, briefing_date)
        return {"id": "page-uuid", "url": "https://www.notion.so/existing-briefing"}

    def fake_append(api_key, database_id, briefing_date, markdown):
        captured["append"] = {
            "api_key": api_key,
            "database_id": database_id,
            "briefing_date": briefing_date,
            "markdown": markdown,
        }
        return "https://www.notion.so/existing-briefing"

    monkeypatch.setattr("web.routers.chat.find_briefing_page", fake_find)
    monkeypatch.setattr("web.routers.chat.append_to_briefing_page", fake_append)

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={
            "date": "2026-05-30",
            "question": "半導体セクターの新着リスクは？",
            "answer": "TSMC の地政学リスクと NVDA 在庫…",
        },
    )

    assert response.status_code == 200
    # AC: returned URL is the existing briefing page, not a freshly created one.
    assert response.json() == {"url": "https://www.notion.so/existing-briefing"}
    assert captured["find"] == ("k-test", "db-test", "2026-05-30")
    assert captured["append"]["api_key"] == "k-test"
    assert captured["append"]["database_id"] == "db-test"
    assert captured["append"]["briefing_date"] == "2026-05-30"
    # Appended markdown mirrors the local notion-import skill's shape:
    # divider + `## 追記: Q&A chat — <ts>` + Question / Answer sub-sections.
    markdown = captured["append"]["markdown"]
    assert markdown.startswith("---\n\n## 追記: Q&A chat —")
    assert "### Question" in markdown
    assert "半導体セクターの新着リスクは？" in markdown
    assert "### Answer" in markdown
    assert "TSMC" in markdown


async def test_chat_notion_import_404_when_briefing_page_missing(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds(monkeypatch)
    monkeypatch.setattr(
        "web.routers.chat.find_briefing_page",
        lambda *a, **kw: None,
    )
    # append must NOT be called when there's no page to append to.
    called = {"append": False}

    def boom(*a, **kw):
        called["append"] = True
        return "noop"

    monkeypatch.setattr("web.routers.chat.append_to_briefing_page", boom)

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 404
    assert "2026-05-30" in response.json()["detail"]
    assert "マーケットブリーフィング" in response.json()["detail"]
    assert called["append"] is False


async def test_chat_notion_import_502_when_append_returns_empty(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds(monkeypatch)
    monkeypatch.setattr(
        "web.routers.chat.find_briefing_page",
        lambda *a, **kw: {"id": "p", "url": "https://www.notion.so/p"},
    )
    monkeypatch.setattr(
        "web.routers.chat.append_to_briefing_page",
        lambda *a, **kw: "",
    )

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 502
    assert "Notion" in response.json()["detail"]


async def test_chat_notion_import_rejects_invalid_date(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds(monkeypatch)
    monkeypatch.setattr("web.routers.chat.find_briefing_page", lambda *a, **kw: None)
    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "../foo", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 422


async def test_chat_notion_import_rejects_empty_answer(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds(monkeypatch)
    monkeypatch.setattr("web.routers.chat.find_briefing_page", lambda *a, **kw: None)
    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": ""},
    )
    assert response.status_code == 422


async def test_chat_notion_import_requires_bearer(async_client):
    response = await async_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 401
