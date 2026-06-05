"""Tests for /api/chat — job-backed POST + GET /stream + DELETE.

Phase-1 contract (#123 / #126):
- ``POST /api/chat`` returns ``202 {job_id, status}`` and schedules the
  subprocess on FastAPI's BackgroundTasks.
- ``GET /api/chat/{job_id}/stream`` replays the buffered events and then
  tails until the job is terminal.
- ``DELETE /api/chat/{job_id}`` terminates the subprocess if still running.

In test mode httpx's TestClient runs the BackgroundTask synchronously
before yielding the response back to the test, so by the time POST
returns the FakePopen has already completed and the job is ``done`` —
which makes the GET-stream assertions deterministic without sleeps.
"""
import asyncio
import io
import time
from unittest.mock import MagicMock

import pytest

from src import chat_job_store, credentials, state as state_mod

pytestmark = pytest.mark.usefixtures("isolated_state")


@pytest.fixture(autouse=True)
def reset_chat_store():
    chat_job_store._reset_for_tests()
    yield
    chat_job_store._reset_for_tests()


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
    """Stand-in for ``subprocess.Popen`` for the chat router tests.

    Iterates the given ``stdout_lines`` from ``proc.stdout``, exposes the
    given stderr/returncode after ``wait()``, and supports ``poll()`` +
    ``terminate()`` so the DELETE path can exercise the running-vs-finished
    distinction.
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
        self.terminated = False

    def wait(self):
        self.returncode = self._returncode
        return self._returncode

    def poll(self):
        # None until ``wait()`` flips it, mirroring real Popen semantics.
        return self.returncode

    def terminate(self):
        self.terminated = True


def _make_popen(stdout_lines=None, stderr=b"", returncode=0):
    """Return a factory closure suitable for monkeypatching subprocess.Popen.

    Records every invocation in ``calls`` for assertions."""
    calls = []

    def factory(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakePopen(cmd, stdout_lines=stdout_lines, stderr=stderr, returncode=returncode)

    factory.calls = calls
    return factory


async def _post_and_drain_stream(client, body) -> tuple[str, str]:
    """POST /api/chat, then GET the stream and return ``(job_id, sse_body)``.

    Asserts the POST returned 202 + a non-empty job_id along the way."""
    post = await client.post("/api/chat", json=body)
    assert post.status_code == 202, post.text
    job_id = post.json()["job_id"]
    assert job_id
    stream = await client.get(f"/api/chat/{job_id}/stream")
    assert stream.status_code == 200
    return job_id, stream.text


# ---------------------------------------------------------------------------
# POST /api/chat — kickoff
# ---------------------------------------------------------------------------


async def test_post_chat_returns_202_with_job_id(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen()
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status"] in ("pending", "running", "done")
    # The job exists in the store after the background task runs.
    assert chat_job_store.get_job(body["job_id"]) is not None


async def test_post_chat_404_when_briefing_missing(authed_client, briefing_setup):
    response = await authed_client.post(
        "/api/chat",
        json={"date": "2099-12-31", "question": "Q?"},
    )
    assert response.status_code == 404


async def test_post_chat_rejects_invalid_date_format(authed_client, briefing_setup):
    """Path-traversal guard: anything that doesn't match YYYY-MM-DD must 422
    before reaching the filesystem."""
    bad_dates = ["../foo", "2026-05", "2026-5-30", "2026-05-30/extra", "abcd-ef-gh"]
    for bad in bad_dates:
        response = await authed_client.post(
            "/api/chat",
            json={"date": bad, "question": "Q?"},
        )
        assert response.status_code == 422, f"expected 422 for date={bad!r}"


async def test_post_chat_rejects_empty_question(authed_client, briefing_setup):
    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": ""},
    )
    assert response.status_code == 422


async def test_post_chat_requires_bearer(async_client, briefing_setup):
    response = await async_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Subprocess invocation — preserved from the pre-#123 contract
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# GET /api/chat/{job_id}/stream — replay + tail
# ---------------------------------------------------------------------------


async def test_chat_stream_returns_sse_content_type(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen(stdout_lines=[b"hello\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    _, _ = await _post_and_drain_stream(
        authed_client, {"date": "2026-05-30", "question": "Q?"}
    )
    # Re-attach to assert the content-type explicitly (the helper already
    # consumed the body once but we just need the header here).
    job = next(iter(chat_job_store._store.values()))  # only one in this test
    stream = await authed_client.get(f"/api/chat/{job.job_id}/stream")
    assert stream.headers["content-type"].startswith("text/event-stream")


async def test_chat_stream_replays_stdout_lines_as_data_events(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen(stdout_lines=[b"line1\n", b"line2\n", b"line3\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    _, body = await _post_and_drain_stream(
        authed_client, {"date": "2026-05-30", "question": "Q?"}
    )

    assert "data: line1\n\n" in body
    assert "data: line2\n\n" in body
    assert "data: line3\n\n" in body


async def test_chat_stream_supports_concurrent_attaches(
    authed_client, briefing_setup, monkeypatch
):
    """Two simultaneous GET streams against the same job both see the full
    transcript. Guards the snapshot path against deque-mutation races and
    confirms a second attach isn't starved by the first."""
    factory = _make_popen(stdout_lines=[b"x\n", b"y\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    post = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    assert post.status_code == 202
    job_id = post.json()["job_id"]

    first, second = await asyncio.gather(
        authed_client.get(f"/api/chat/{job_id}/stream"),
        authed_client.get(f"/api/chat/{job_id}/stream"),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    for line in ("x", "y"):
        assert f"data: {line}\n\n" in first.text
        assert f"data: {line}\n\n" in second.text


async def test_chat_job_marked_failed_when_popen_raises(
    authed_client, briefing_setup, monkeypatch
):
    """If ``subprocess.Popen`` itself raises, the job must end up ``failed``
    (rather than leaking in ``running``) and the SSE stream must surface an
    ``error`` event so clients close cleanly instead of polling forever."""
    def _boom(*args, **kwargs):
        raise FileNotFoundError("claude binary missing")

    monkeypatch.setattr("web.routers.chat.subprocess.Popen", _boom)

    response = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job = chat_job_store.get_job(job_id)
    assert job is not None
    assert job.status == "failed"
    assert "claude binary missing" in (job.error or "")

    stream = await authed_client.get(f"/api/chat/{job_id}/stream")
    assert stream.status_code == 200
    assert "event: error" in stream.text
    assert "claude binary missing" in stream.text


async def test_chat_stream_can_be_reattached_to_replay_buffer(
    authed_client, briefing_setup, monkeypatch
):
    """Survives a client disconnect: a second GET against the same job_id
    sees every event from the start. This is the core #112 / #126 win —
    a tab switch or page reload no longer drops the in-flight answer."""
    factory = _make_popen(stdout_lines=[b"a\n", b"b\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    job_id, first = await _post_and_drain_stream(
        authed_client, {"date": "2026-05-30", "question": "Q?"}
    )
    second = await authed_client.get(f"/api/chat/{job_id}/stream")
    assert second.status_code == 200
    body = second.text

    # Both attaches receive the full transcript.
    for line in ("a", "b"):
        assert f"data: {line}\n\n" in first
        assert f"data: {line}\n\n" in body


async def test_get_chat_stream_404_when_job_unknown(authed_client, briefing_setup):
    response = await authed_client.get("/api/chat/does-not-exist/stream")
    assert response.status_code == 404


async def test_chat_stream_strips_trailing_cr_from_stdout_lines(
    authed_client, briefing_setup, monkeypatch
):
    """Windows-style \\r\\n line endings must not leak into the SSE event."""
    factory = _make_popen(stdout_lines=[b"hello world\r\n", b"line2\r\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    _, body = await _post_and_drain_stream(
        authed_client, {"date": "2026-05-30", "question": "Q?"}
    )
    assert "\r\n\n" not in body
    assert "data: hello world\n\n" in body
    assert "data: line2\n\n" in body


async def test_chat_stream_stale_session_deletes_file_and_emits_event(
    authed_client, briefing_setup, monkeypatch
):
    session_file = briefing_setup / ".sessions" / "2026-05-30"
    session_file.write_text("stale-uuid")

    factory = _make_popen(
        stderr=b"No conversation found with session ID: stale-uuid\n",
        returncode=1,
    )
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    _, body = await _post_and_drain_stream(
        authed_client, {"date": "2026-05-30", "question": "Q?"}
    )

    assert "event: stale_session" in body
    assert not session_file.exists()


async def test_chat_stream_other_subprocess_error_emits_error_event(
    authed_client, briefing_setup, monkeypatch
):
    factory = _make_popen(stderr=b"auth failed", returncode=1)
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    _, body = await _post_and_drain_stream(
        authed_client, {"date": "2026-05-30", "question": "Q?"}
    )

    assert "event: error" in body
    assert "auth failed" in body


async def test_chat_stream_multi_line_stderr_emits_one_data_per_line(
    authed_client, briefing_setup, monkeypatch
):
    """Per SSE spec, an event with multi-line content needs one `data:` prefix
    per line — a single `data:` with embedded \\n breaks compliant parsers."""
    factory = _make_popen(stderr=b"err line 1\nerr line 2\nerr line 3", returncode=1)
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    _, body = await _post_and_drain_stream(
        authed_client, {"date": "2026-05-30", "question": "Q?"}
    )
    assert "event: error\n" in body
    assert "data: err line 1\n" in body
    assert "data: err line 2\n" in body
    assert "data: err line 3\n" in body


# ---------------------------------------------------------------------------
# DELETE /api/chat/{job_id} — cancel
# ---------------------------------------------------------------------------


async def test_delete_chat_terminates_running_subprocess(authed_client):
    """Setting up a job directly (skip POST) gives us a Popen handle whose
    ``poll()`` still returns ``None`` so the cancel path actually fires."""
    job = chat_job_store.create_job()
    fake = MagicMock(spec=["poll", "terminate"])
    fake.poll.return_value = None
    chat_job_store.attach_process(job.job_id, fake)

    response = await authed_client.delete(f"/api/chat/{job.job_id}")
    assert response.status_code == 204
    fake.terminate.assert_called_once()


async def test_delete_chat_idempotent_when_subprocess_already_exited(authed_client):
    job = chat_job_store.create_job()
    fake = MagicMock(spec=["poll", "terminate"])
    fake.poll.return_value = 0  # already exited
    chat_job_store.attach_process(job.job_id, fake)

    response = await authed_client.delete(f"/api/chat/{job.job_id}")
    assert response.status_code == 204
    fake.terminate.assert_not_called()


async def test_delete_chat_idempotent_when_job_missing(authed_client):
    response = await authed_client.delete("/api/chat/does-not-exist")
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# Grace-timer GC after completion
# ---------------------------------------------------------------------------


async def test_chat_job_is_gc_after_grace_period(
    authed_client, briefing_setup, monkeypatch
):
    # Tiny grace so the test doesn't have to wait. The runner reads
    # CHAT_JOB_GC_GRACE_SEC from the module namespace at call time, so
    # patching the module attribute before POST takes effect.
    monkeypatch.setattr("web.routers.chat.CHAT_JOB_GC_GRACE_SEC", 0.05)

    factory = _make_popen(stdout_lines=[b"hi\n"])
    monkeypatch.setattr("web.routers.chat.subprocess.Popen", factory)

    post = await authed_client.post(
        "/api/chat",
        json={"date": "2026-05-30", "question": "Q?"},
    )
    job_id = post.json()["job_id"]
    assert chat_job_store.get_job(job_id) is not None

    # Poll instead of one fixed sleep: a fixed 0.25s wait is flaky on
    # busy CI where Timer scheduling can be delayed past that window.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if chat_job_store.get_job(job_id) is None:
            break
        time.sleep(0.05)
    assert chat_job_store.get_job(job_id) is None


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
