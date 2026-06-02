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
# POST /api/chat/notion-import — delegates to /notion-import skill via claude CLI
# ---------------------------------------------------------------------------


def _seed_notion_creds():
    from src import credentials as cred_mod
    cred_mod.set_credential("NOTION_API_KEY", "k-test")
    cred_mod.set_credential("NOTION_DATABASE_ID", "db-test")


def _stream_json_result(text: str) -> str:
    """Build a minimal --output-format stream-json stdout containing a result
    record with the given final text."""
    import json as _json
    return _json.dumps({"type": "result", "subtype": "success", "result": text}) + "\n"


def _fake_run_factory(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Return a fake subprocess.run that records the call and returns a
    CompletedProcess-shaped object. The first positional arg (cmd list) is
    captured into `.calls` so tests can assert on flags / model selection."""
    calls: list[dict] = []

    class _Result:
        def __init__(self):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    def factory(cmd, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        return _Result()

    factory.calls = calls  # type: ignore[attr-defined]
    return factory


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


async def test_chat_notion_import_success_invokes_skill_and_extracts_url(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    page_url = "https://www.notion.so/created-page-abc123"
    factory = _fake_run_factory(
        stdout=_stream_json_result(
            f"追記しました。\nNotion: {page_url}\n保存: output/chat-2026-05-30_2026-05-30.md"
        ),
        returncode=0,
    )
    monkeypatch.setattr("web.routers.chat.subprocess.run", factory)
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={
            "date": "2026-05-30",
            "question": "半導体セクターの新着リスクは？",
            "answer": "TSMC の地政学リスクと NVDA 在庫…",
            "model": "opus",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"] == page_url
    assert "追記しました" in payload["summary"]

    # The CLI invocation must carry the slash command, the model selection,
    # bypass perms, stream-json output, and an --add-dir for skill discovery.
    cmd = factory.calls[0]["cmd"]
    prompt = cmd[cmd.index("-p") + 1]
    assert "/notion-import chat-2026-05-30" in prompt
    assert "半導体セクターの新着リスクは？" in prompt
    assert "TSMC" in prompt
    assert "bypassPermissions" in cmd
    assert "stream-json" in cmd
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert "--add-dir" in cmd
    # Notion credentials must reach the subprocess env so a non-MCP fallback
    # path (e.g. notion-client reading env directly) can still authenticate.
    env = factory.calls[0]["kwargs"]["env"]
    assert env.get("NOTION_API_KEY") == "k-test"
    assert env.get("NOTION_DATABASE_ID") == "db-test"


async def test_chat_notion_import_defaults_to_sonnet_model(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    factory = _fake_run_factory(
        stdout=_stream_json_result("done https://www.notion.so/abc"),
        returncode=0,
    )
    monkeypatch.setattr("web.routers.chat.subprocess.run", factory)
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")

    await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )

    cmd = factory.calls[0]["cmd"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"


async def test_chat_notion_import_rejects_unknown_model(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")
    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!", "model": "gpt-4"},
    )
    assert response.status_code == 422


async def test_chat_notion_import_404_when_skill_reports_no_briefing_page(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    # Skill ran cleanly (rc=0) but the result text contains no Notion URL —
    # SKILL.md mandates this when the page isn't found.
    factory = _fake_run_factory(
        stdout=_stream_json_result(
            "対象ページが見つかりませんでした: マーケットブリーフィング — 2026-05-30"
        ),
        returncode=0,
    )
    monkeypatch.setattr("web.routers.chat.subprocess.run", factory)
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 404
    # Skill's own report is echoed verbatim so the operator sees why.
    assert "2026-05-30" in response.json()["detail"]
    assert "対象ページが見つかりません" in response.json()["detail"]


async def test_chat_notion_import_502_when_cli_exits_nonzero(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    factory = _fake_run_factory(
        stdout="",
        stderr="claude: authentication failed",
        returncode=1,
    )
    monkeypatch.setattr("web.routers.chat.subprocess.run", factory)
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 502
    assert "rc=1" in response.json()["detail"]


async def test_chat_notion_import_502_when_claude_binary_missing(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: None)

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 502
    assert "claude CLI not found" in response.json()["detail"]


async def test_chat_notion_import_502_on_subprocess_timeout(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    import subprocess as sp
    _seed_notion_creds()

    def raise_timeout(*a, **kw):
        raise sp.TimeoutExpired(cmd=a[0] if a else [], timeout=120)

    monkeypatch.setattr("web.routers.chat.subprocess.run", raise_timeout)
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")

    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "2026-05-30", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 502
    assert "did not finish" in response.json()["detail"]


async def test_chat_notion_import_rejects_invalid_date(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")
    response = await authed_client.post(
        "/api/chat/notion-import",
        json={"date": "../foo", "question": "Q?", "answer": "A!"},
    )
    assert response.status_code == 422


async def test_chat_notion_import_rejects_empty_answer(
    authed_client, isolated_keyring, clear_credential_env, monkeypatch
):
    _seed_notion_creds()
    monkeypatch.setattr("web.routers.chat.shutil.which", lambda _: "/fake/bin/claude")
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
