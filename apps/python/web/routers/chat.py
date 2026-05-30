"""POST /api/chat — SSE streaming Q&A against a daily briefing.

The endpoint spawns the same ``claude`` CLI invocation that
``bin/chat.py`` uses (via the shared ``src.chat_session.build_cmd`` helper)
and streams its stdout line-by-line as Server-Sent Events.

Stale-session handling: if a saved session id can no longer be resumed
(claude exits with the sentinel ``"No conversation found"``) the stale
``.sessions/<date>`` file is deleted and an SSE event ``stale_session``
is emitted. The frontend should re-issue the same request, which will
then create a fresh session because the file is gone. We do NOT retry
in-stream because once any stdout has been emitted to the client there
is no clean way to "rewind" the SSE stream.

``ANTHROPIC_API_KEY`` propagation follows ``state.read_state().auth_mode``
via ``claude_runner.build_env`` — same toggle used by ``run_claude``.

Stderr is drained in a background thread to avoid a pipe-buffer deadlock
(if stderr ever exceeded the OS pipe buffer ~64KB without being read,
claude would block writing and stdout streaming would stall).
"""
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src import state as state_mod
from src.chat_session import build_cmd
from src.claude_runner import build_env
from web.auth import require_bearer

PYTHON_APP = Path(__file__).resolve().parents[2]  # apps/python/
BRIEFING_DIR = PYTHON_APP / "output" / "briefing"
SESSIONS_DIR = BRIEFING_DIR / ".sessions"

router = APIRouter(dependencies=[Depends(require_bearer)])


class ChatBody(BaseModel):
    # Pinned to YYYY-MM-DD so user input can't path-traverse into
    # SESSIONS_DIR (e.g. "../foo").
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    question: str = Field(min_length=1)


def _sse_event(content: str, event: str | None = None) -> bytes:
    """Build a well-formed SSE event from possibly multi-line content.

    Per the SSE spec, multi-line content needs one ``data:`` prefix per
    line; an empty trailing line terminates the event."""
    out: list[str] = []
    if event:
        out.append(f"event: {event}")
    for line in content.splitlines() or [""]:
        out.append(f"data: {line}")
    return ("\n".join(out) + "\n\n").encode("utf-8")


def _stream(cmd: list[str], session_file: Path, env: dict[str, str]) -> Iterator[bytes]:
    """Pipe claude's stdout to SSE bytes; detect the stale-session sentinel."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Drain stderr concurrently — without this, a large stderr write would
    # fill the OS pipe buffer, block claude, and stall the stdout iteration.
    stderr_chunks: list[bytes] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for chunk in iter(lambda: proc.stderr.read(4096), b""):
            stderr_chunks.append(chunk)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        assert proc.stdout is not None
        for line_bytes in proc.stdout:
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            yield _sse_event(line)
    finally:
        proc.wait()
        stderr_thread.join(timeout=2)

    if proc.returncode != 0:
        stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        is_resume = "--resume" in cmd
        if is_resume and "No conversation found" in stderr:
            session_file.unlink(missing_ok=True)
            yield _sse_event(
                "saved session expired; retry the request",
                event="stale_session",
            )
        else:
            yield _sse_event(stderr.strip(), event="error")


@router.post("/chat")
def post_chat(body: ChatBody) -> StreamingResponse:
    briefing_file = BRIEFING_DIR / f"briefing_{body.date}.md"
    session_file = SESSIONS_DIR / body.date

    if not briefing_file.exists():
        raise HTTPException(status_code=404, detail=f"no briefing for {body.date}")

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = build_cmd(body.date, briefing_file, session_file) + ["-p", body.question]
    env = build_env(auth_mode=state_mod.read_state().auth_mode)

    return StreamingResponse(
        _stream(cmd, session_file, env),
        media_type="text/event-stream",
    )
