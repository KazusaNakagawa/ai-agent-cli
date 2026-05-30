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
via ``claude_runner._build_env`` — same toggle used by ``run_claude``.
"""
import subprocess
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src import state as state_mod
from src.chat_session import build_cmd
from src.claude_runner import _build_env
from web.auth import require_bearer

PYTHON_APP = Path(__file__).resolve().parents[2]  # apps/python/
BRIEFING_DIR = PYTHON_APP / "output" / "briefing"
SESSIONS_DIR = BRIEFING_DIR / ".sessions"

router = APIRouter(dependencies=[Depends(require_bearer)])


class ChatBody(BaseModel):
    date: str
    question: str


def _stream(cmd: list[str], session_file: Path, env: dict[str, str]) -> Iterator[bytes]:
    """Pipe claude's stdout to SSE bytes; detect the stale-session sentinel."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        for line_bytes in proc.stdout:
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
            yield f"data: {line}\n\n".encode("utf-8")
    finally:
        proc.wait()

    if proc.returncode != 0:
        stderr = (proc.stderr.read() or b"").decode("utf-8", errors="replace")
        is_resume = "--resume" in cmd
        if is_resume and "No conversation found" in stderr:
            session_file.unlink(missing_ok=True)
            yield b"event: stale_session\ndata: saved session expired; retry the request\n\n"
        else:
            yield f"event: error\ndata: {stderr.strip()}\n\n".encode("utf-8")


@router.post("/chat")
def post_chat(body: ChatBody) -> StreamingResponse:
    briefing_file = BRIEFING_DIR / f"briefing_{body.date}.md"
    session_file = SESSIONS_DIR / body.date

    if not briefing_file.exists():
        raise HTTPException(status_code=404, detail=f"no briefing for {body.date}")

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = build_cmd(body.date, briefing_file, session_file) + ["-p", body.question]
    env = _build_env(auth_mode=state_mod.read_state().auth_mode)

    return StreamingResponse(
        _stream(cmd, session_file, env),
        media_type="text/event-stream",
    )
