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

POST /api/chat/notion-import: delegates to the local ``/notion-import``
skill via the ``claude`` CLI (subprocess + ``--output-format stream-json``),
so the skill definition under ``.claude/skills/notion-import/SKILL.md``
remains the single source of truth — no duplicate Python implementation.
"""
import json
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src import credentials as cred_mod
from src import state as state_mod
from src.chat_session import build_cmd
from src.claude_runner import build_env
from src.logger import get_logger
from web.auth import require_bearer

logger = get_logger(__name__)
# apps/python/web/routers/chat.py → repo root is parents[3] (chat.py → routers → web → python → apps → repo).
REPO_ROOT = Path(__file__).resolve().parents[4]
NOTION_URL_RE = re.compile(r"https://www\.notion\.so/[A-Za-z0-9\-]+")
NOTION_IMPORT_TIMEOUT_SEC = 120
# Allow-list of model aliases the user can pick from the UI. Anything else
# is rejected at the schema level so a malicious payload can't make us spawn
# a claude subprocess pinned to an unintended model.
ChatNotionImportModel = Literal["sonnet", "opus", "haiku"]

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


class ChatNotionImportBody(BaseModel):
    # Same path-traversal guard as ChatBody; the date scopes the briefing page.
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    model: ChatNotionImportModel = "sonnet"


class ChatNotionImportResponse(BaseModel):
    url: str
    summary: str = ""


def _build_skill_prompt(body: ChatNotionImportBody) -> str:
    """Compose the prompt we pass to ``claude -p`` so it runs the skill.

    The skill reads the *preceding assistant answer* as its source of truth,
    so we surface the Q&A inline in the prompt and explicitly call out the
    slash command + the briefing-page hint the skill expects.
    """
    slug = f"chat-{body.date}"
    return (
        f"以下の Q&A を `/notion-import {slug}` スキルで Notion の "
        f"「マーケットブリーフィング — {body.date}」ページ末尾に追記してください。\n"
        "対象ページが見つからない場合は SKILL の手順どおり処理を停止し、その旨を簡潔に報告してください。\n\n"
        "## Question\n"
        f"{body.question}\n\n"
        "## Answer\n"
        f"{body.answer}\n"
    )


def _extract_final_text(stream_json_stdout: str) -> str:
    """Pick the final assistant text out of a ``--output-format stream-json`` blob.

    The CLI emits one JSON object per line. The terminal record is
    ``{"type":"result", "subtype":"success"|..., "result":"<text>"}``;
    its ``result`` field is exactly what an interactive ``claude -p`` would
    have printed, which is also where the skill surfaces the final Notion URL.
    """
    final = ""
    for line in stream_json_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "result":
            final = obj.get("result", "") or ""
    return final


@router.post("/chat/notion-import", response_model=ChatNotionImportResponse)
def post_chat_notion_import(body: ChatNotionImportBody) -> ChatNotionImportResponse:
    """Delegate the save to the local `/notion-import` skill via the CLI.

    Status map:
      400 — NOTION_API_KEY / NOTION_DATABASE_ID not configured
      404 — skill ran but reported no briefing page for the date
      502 — claude CLI failed (non-zero exit, missing binary, timeout, or no URL surfaced)

    The skill itself owns the Notion page lookup + append logic. This
    endpoint only orchestrates the subprocess and surfaces whatever the
    skill reports back.
    """
    # AC: short-circuit with a descriptive message so the UI can tell the
    # operator exactly which credential to set, rather than letting the
    # subprocess fail opaquely deep inside the MCP call.
    api_key = cred_mod.get_credential("NOTION_API_KEY")
    database_id = cred_mod.get_credential("NOTION_DATABASE_ID")
    missing = [
        name
        for name, value in (
            ("NOTION_API_KEY", api_key),
            ("NOTION_DATABASE_ID", database_id),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Notion credentials not configured: {', '.join(missing)}",
        )

    claude_path = shutil.which("claude")
    if claude_path is None:
        raise HTTPException(
            status_code=502,
            detail="claude CLI not found on PATH — install Claude Code to enable Notion save.",
        )

    cmd = [
        claude_path,
        "-p",
        _build_skill_prompt(body),
        "--permission-mode", "bypassPermissions",
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(REPO_ROOT),
        "--model", body.model,
    ]
    env = build_env(auth_mode=state_mod.read_state().auth_mode)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=NOTION_IMPORT_TIMEOUT_SEC,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        logger.error("notion-import skill timed out after %ds", NOTION_IMPORT_TIMEOUT_SEC)
        raise HTTPException(
            status_code=502,
            detail=f"The /notion-import skill did not finish within {NOTION_IMPORT_TIMEOUT_SEC}s.",
        ) from None

    if result.returncode != 0:
        stderr = (result.stderr or "")[:500]
        logger.error("claude CLI exited rc=%d during notion-import: %s", result.returncode, stderr)
        raise HTTPException(
            status_code=502,
            detail=f"claude CLI failed (rc={result.returncode}). Check the server logs.",
        )

    final_text = _extract_final_text(result.stdout)
    url_match = NOTION_URL_RE.search(final_text)
    if not url_match:
        # The skill ran but didn't surface a Notion URL — most commonly because
        # the target briefing page doesn't exist. SKILL.md explicitly tells the
        # model to "stop and report" in that case, so we map this to 404 and
        # echo the model's report so the operator sees the actual reason.
        snippet = final_text.strip().splitlines()
        report = " ".join(snippet)[:300] if snippet else "(no output)"
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Notion briefing page found for {body.date} "
                f"(skill report: {report})"
            ),
        )

    return ChatNotionImportResponse(url=url_match.group(0), summary=final_text.strip()[:500])


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
