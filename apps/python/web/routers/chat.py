"""POST /api/chat + GET /api/chat/{job_id}/stream — job-backed Q&A.

The endpoint kicks off the same ``claude`` CLI invocation that
``bin/chat.py`` uses (via the shared ``src.chat_session.build_cmd`` helper)
and streams its stdout line-by-line as Server-Sent Events. As of #123
the streaming is split from the kickoff so a chat answer survives a tab
switch or page reload (Epic #126):

- ``POST /api/chat`` creates a ``ChatJob`` in ``src.chat_job_store``,
  schedules the subprocess on FastAPI's ``BackgroundTasks``, and returns
  ``202 {job_id, status}`` — mirrors ``POST /api/run``.
- The background runner spawns ``claude``, appends each stdout line as
  an SSE-encoded event into the job's bounded replay buffer, then marks
  the job ``done`` / ``failed``.
- ``GET /api/chat/{job_id}/stream`` opens an SSE response that first
  replays every buffered event (so a reconnecting client doesn't miss
  the start of the answer) and then tails new events until the job's
  status is terminal.
- ``DELETE /api/chat/{job_id}`` terminates the subprocess if it's still
  running. The cancel path is idempotent and quiet on already-finished
  jobs.

The subprocess intentionally does **not** die on client SSE disconnect —
a new GET against the same ``job_id`` simply re-attaches and replays.
After completion the job is GC'd from the in-memory store on a grace
timer (default ~120s) so we don't accumulate dead buffers.

Stale-session handling: if a saved session id can no longer be resumed
(claude exits with the sentinel ``"No conversation found"``) the stale
``.sessions/<date>`` file is deleted and a ``stale_session`` SSE event
is appended to the job's buffer. The frontend re-issues the POST, which
creates a fresh session because the file is gone. We do NOT retry
in-stream because once any stdout has been emitted there is no clean
way to "rewind" the SSE stream.

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
import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src import chat_job_store
from src import credentials as cred_mod
from src import journal_store
from src import state as state_mod
from src.chat_session import build_cmd, build_journal_cmd
from src.claude_runner import build_env
from src.claude_stream import StreamState, consume_stream_line
from src.logger import get_logger
from src.usage_logger import log_usage
from web.auth import require_bearer

logger = get_logger(__name__)
# apps/python/web/routers/chat.py → repo root is parents[3] (chat.py → routers → web → python → apps → repo).
REPO_ROOT = Path(__file__).resolve().parents[4]
IMAGES_ROOT = REPO_ROOT / "apps" / "python" / "input" / "images"
NOTION_URL_RE = re.compile(r"https://www\.notion\.so/[A-Za-z0-9\-]+")
NOTION_IMPORT_TIMEOUT_SEC = 120
# Allow-list of model aliases the user can pick from the UI. Anything else
# is rejected at the schema level so a malicious payload can't make us spawn
# a claude subprocess pinned to an unintended model.
ChatNotionImportModel = Literal["sonnet", "opus", "haiku"]

PYTHON_APP = Path(__file__).resolve().parents[2]  # apps/python/
BRIEFING_DIR = PYTHON_APP / "output" / "briefing"
SESSIONS_DIR = BRIEFING_DIR / ".sessions"

# Drop a completed chat job from the store this many seconds after its
# subprocess exits. The buffer keeps replay working for a short reconnect
# window; longer than this and we'd accumulate dead buffers in memory.
CHAT_JOB_GC_GRACE_SEC = 120.0
# How long ``_tail_events`` sleeps between polls when waiting for new
# events on a running job. Small enough to feel live, large enough not
# to spin a CPU per attached client.
_TAIL_POLL_INTERVAL_SEC = 0.05

# --output-format stream-json lets us capture the per-call ``usage`` record
# (token counts + cost) that plain-text output discards, so chat/journal turns
# can be surfaced in the usage dashboard. ``--verbose`` is required by the CLI
# for stream-json under ``-p``; ``--include-partial-messages`` preserves the
# incremental (line-by-line) streaming the SSE client already expects.
CHAT_STREAM_FLAGS = [
    "--output-format", "stream-json",
    "--verbose",
    "--include-partial-messages",
]

router = APIRouter(dependencies=[Depends(require_bearer)])


def _validate_image_path(image_path: str | None) -> Path | None:
    """Return resolved Path if image_path is inside IMAGES_ROOT, else raise 400."""
    if image_path is None:
        return None
    resolved = Path(image_path).resolve()
    if not str(resolved).startswith(str(IMAGES_ROOT) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid image path")
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Image file not found")
    return resolved


# Reading a base64 image requires the stream-json *input* format. The default
# "text" input treats piped stdin as a plain prompt string, so the JSON (and
# the image) is never parsed — claude just sees gibberish. Pairs with the
# stream-json output already in CHAT_STREAM_FLAGS.
IMAGE_INPUT_FLAGS = ["--input-format", "stream-json"]

_IMAGE_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _build_image_message(img_path: Path, question: str) -> str:
    """Build a stream-json input envelope carrying a base64 image + the question.

    The claude CLI's stream-json input expects newline-delimited
    ``{"type":"user","message":{...}}`` objects whose ``content`` uses the
    Messages API block format. The trailing newline terminates the record.
    """
    b64 = base64.b64encode(img_path.read_bytes()).decode()
    ext = img_path.suffix.lstrip(".").lower()
    media = _IMAGE_MEDIA_TYPES.get(ext, "image/png")
    return json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
                {"type": "text", "text": question},
            ],
        },
    }) + "\n"


class ChatBody(BaseModel):
    # Pinned to YYYY-MM-DD so user input can't path-traverse into
    # SESSIONS_DIR (e.g. "../foo").
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    question: str = Field(min_length=1)
    image_path: str | None = None


class ChatPostResponse(BaseModel):
    job_id: str
    status: str


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



def _run_chat_job(
    job_id: str,
    cmd: list[str],
    session_file: Path,
    env: dict[str, str],
    label: str,
    image_message: str | None = None,
) -> None:
    """Background task: drive the claude subprocess to completion and
    append each stdout line into the job's replay buffer.

    Always advances the job through running → done / failed regardless of
    exception path. A grace-timer GC is scheduled at the end so memory
    doesn't grow per-request.
    """
    chat_job_store.mark_running(job_id)
    try:
        stdin_mode = subprocess.PIPE if image_message else subprocess.DEVNULL
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=stdin_mode,
            env=env,
        )
        if image_message:
            if proc.stdin is not None:
                proc.stdin.write(image_message.encode())
                proc.stdin.close()
        chat_job_store.attach_process(job_id, proc)

        # Drain stderr concurrently — without this, a large stderr write would
        # fill the OS pipe buffer, block claude, and stall the stdout iteration.
        stderr_chunks: list[bytes] = []

        def _drain_stderr() -> None:
            assert proc.stderr is not None
            for chunk in iter(lambda: proc.stderr.read(4096), b""):
                stderr_chunks.append(chunk)

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        state = StreamState()
        try:
            assert proc.stdout is not None
            for line_bytes in proc.stdout:
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    continue
                for text_line in consume_stream_line(line, state):
                    chat_job_store.append_event(job_id, _sse_event(text_line))
        finally:
            proc.wait()
            stderr_thread.join(timeout=2)
            chat_job_store.detach_process(job_id)

        # Flush the final partial line (a text block with no trailing newline).
        if state.text_buf:
            chat_job_store.append_event(job_id, _sse_event(state.text_buf))
        # Record token usage for this turn (best-effort; must never fail the job).
        if state.usage is not None:
            try:
                log_usage(
                    label=label,
                    usage=state.usage,
                    cost_usd=state.cost_usd,
                    duration_ms=state.duration_ms,
                )
            except Exception:  # noqa: BLE001
                logger.warning("failed to record usage log [%s]", label, exc_info=True)

        if proc.returncode != 0:
            stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            is_resume = "--resume" in cmd
            if is_resume and "No conversation found" in stderr:
                # Stale saved session: drop the file so the next POST creates a
                # fresh one, and tell the client to retry. The job itself is
                # still considered "done" (not "failed") because the user-facing
                # remediation is a quiet retry, not an error to surface.
                session_file.unlink(missing_ok=True)
                chat_job_store.append_event(
                    job_id,
                    _sse_event(
                        "saved session expired; retry the request",
                        event="stale_session",
                    ),
                )
                chat_job_store.mark_done(job_id)
            else:
                chat_job_store.append_event(
                    job_id, _sse_event(stderr.strip(), event="error")
                )
                chat_job_store.mark_failed(
                    job_id, stderr.strip() or "chat subprocess failed"
                )
        else:
            chat_job_store.mark_done(job_id)
    except Exception as exc:
        # Catch-all so a Popen / OSError / etc. before we reach the normal
        # done/failed branches can't leave the job stuck in ``running``.
        logger.exception("chat job %s crashed before normal completion", job_id)
        chat_job_store.append_event(job_id, _sse_event(str(exc), event="error"))
        chat_job_store.mark_failed(job_id, str(exc) or exc.__class__.__name__)
    finally:
        _schedule_gc(job_id, CHAT_JOB_GC_GRACE_SEC)


def _schedule_gc(job_id: str, delay_sec: float) -> None:
    """Schedule the job's removal from the in-memory store after the grace
    period. Daemon timer so it doesn't block uvicorn shutdown."""
    timer = threading.Timer(delay_sec, lambda: chat_job_store.remove_job(job_id))
    timer.daemon = True
    timer.start()


def _tail_events(job_id: str) -> Iterator[bytes]:
    """Yield SSE events from a chat job: first replay every buffered event,
    then poll for new ones until the job reaches a terminal status. Each
    event is tagged with a monotonic seq id (see ``chat_job_store``), so a
    re-attaching client doesn't see duplicates even if the buffer was
    partially drained between attaches in the same connection.
    """
    last_seq = 0
    while True:
        new_events, status = chat_job_store.snapshot_events_since(job_id, last_seq)

        if status is None:
            # GC'd while we were tailing — emit a terminal hint so the
            # client closes cleanly rather than seeing a connection drop.
            yield _sse_event("job no longer available", event="error")
            return

        for seq, event_bytes in new_events:
            yield event_bytes
            last_seq = seq

        if status in ("done", "failed"):
            return

        time.sleep(_TAIL_POLL_INTERVAL_SEC)


@router.post("/chat", status_code=202, response_model=ChatPostResponse)
def post_chat(body: ChatBody, background_tasks: BackgroundTasks) -> ChatPostResponse:
    """Create a chat job and schedule the subprocess. Returns immediately
    with the ``job_id`` so the client can open a GET stream against it."""
    briefing_file = BRIEFING_DIR / f"briefing_{body.date}.md"
    session_file = SESSIONS_DIR / body.date

    if not briefing_file.exists():
        raise HTTPException(status_code=404, detail=f"no briefing for {body.date}")

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    img_path = _validate_image_path(body.image_path)
    image_message: str | None = None
    if img_path:
        image_message = _build_image_message(img_path, body.question)
        cmd = [*build_cmd(body.date, briefing_file, session_file), "-p", *IMAGE_INPUT_FLAGS, *CHAT_STREAM_FLAGS]
    else:
        cmd = [*build_cmd(body.date, briefing_file, session_file), "-p", body.question, *CHAT_STREAM_FLAGS]
    env = build_env(auth_mode=state_mod.read_state().auth_mode)

    job = chat_job_store.create_job()
    background_tasks.add_task(_run_chat_job, job.job_id, cmd, session_file, env, "chat", image_message)
    return ChatPostResponse(job_id=job.job_id, status=job.status)


# Upper bound on the assembled journal context. Caps the size of the
# --append-system-prompt payload (and the token cost) for users with many or
# very long entries. Newest entries are kept; older ones are dropped once the
# budget is exhausted.
JOURNAL_CONTEXT_MAX_CHARS = 40_000


class JournalChatBody(BaseModel):
    question: str = Field(min_length=1)
    # How many most-recent journal days to load as brainstorm context.
    days: int = Field(default=7, ge=1, le=31)
    image_path: str | None = None


def _gather_journal_context(days: int, max_chars: int | None = None) -> str:
    """Concatenate journal entries from the newest ``days`` dates into a blob.

    Selection is day-based: all entries whose date falls in the most recent
    ``days`` distinct dates are included (a single date may hold several
    per-entry files). Entries are appended newest-first and the blob is capped
    at ``max_chars`` (defaults to the module-level ``JOURNAL_CONTEXT_MAX_CHARS``)
    so a long history can't blow up the prompt; entries past the budget are
    dropped. The whole blob is wrapped as untrusted input by ``build_journal_cmd``.
    """
    if max_chars is None:
        max_chars = JOURNAL_CONTEXT_MAX_CHARS
    # Walk entries newest-first, keeping every entry that belongs to one of the
    # newest ``days`` distinct dates so multiple entries per day are preserved.
    seen_dates: set[str] = set()
    sections: list[str] = []
    total = 0
    for entry_id, _ in journal_store.list_files():
        date = journal_store.date_of(entry_id)
        if date not in seen_dates:
            if len(seen_dates) >= days:
                break
            seen_dates.add(date)
        content = journal_store.read_entry(entry_id)
        if not content:
            continue
        section = content.strip()
        # +2 accounts for the "\n\n" join separator between sections.
        if sections and total + len(section) + 2 > max_chars:
            break
        sections.append(section)
        total += len(section) + 2
    return "\n\n".join(sections)


@router.post("/journal/chat", status_code=202, response_model=ChatPostResponse)
def post_journal_chat(
    body: JournalChatBody, background_tasks: BackgroundTasks
) -> ChatPostResponse:
    """Start a journaling brainstorm chat seeded with recent journal entries.

    Reuses the chat job/stream machinery: the returned ``job_id`` is streamed
    via ``GET /api/chat/{job_id}/stream`` and cancelled via ``DELETE``.
    """
    context = _gather_journal_context(body.days)
    if not context:
        raise HTTPException(status_code=404, detail="no journal entries to brainstorm over")

    today = journal_store.today()
    sessions_dir = journal_store.JOURNAL_DIR / ".sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / today

    img_path = _validate_image_path(body.image_path)
    image_message: str | None = None
    if img_path:
        image_message = _build_image_message(img_path, body.question)
        cmd = [*build_journal_cmd(today, context, session_file), "-p", *IMAGE_INPUT_FLAGS, *CHAT_STREAM_FLAGS]
    else:
        cmd = [*build_journal_cmd(today, context, session_file), "-p", body.question, *CHAT_STREAM_FLAGS]
    env = build_env(auth_mode=state_mod.read_state().auth_mode)

    job = chat_job_store.create_job()
    background_tasks.add_task(_run_chat_job, job.job_id, cmd, session_file, env, "journal", image_message)
    return ChatPostResponse(job_id=job.job_id, status=job.status)


@router.get("/chat/{job_id}/stream")
def get_chat_stream(job_id: str) -> StreamingResponse:
    """Open an SSE stream against a chat job. Replays the full buffer then
    tails until terminal status. 404 if the job doesn't exist (already
    GC'd or never created)."""
    job = chat_job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"chat job not found: {job_id}")
    return StreamingResponse(
        _tail_events(job_id),
        media_type="text/event-stream",
    )


@router.delete("/chat/{job_id}", status_code=204)
def delete_chat(job_id: str) -> None:
    """Cancel an in-flight chat job by terminating its subprocess.

    Idempotent: a 204 comes back even if the job has already finished or
    been GC'd, so the frontend doesn't need to special-case races.
    """
    job = chat_job_store.get_job(job_id)
    if job is None:
        return
    proc = job.process
    if proc is None or proc.poll() is not None:
        # Already exited or was never attached — nothing to terminate.
        return
    try:
        proc.terminate()
    except Exception as exc:
        # If terminate() blew up, the runner's proc.wait() can hang and the
        # job would otherwise stay ``running`` forever — explicitly fail it
        # so the GET stream can close and the GC timer eventually clears it.
        logger.exception("failed to terminate chat subprocess (job_id=%s)", job_id)
        chat_job_store.mark_failed(job_id, f"terminate failed: {exc}")


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


def _append_to_local_briefing(date: str, question: str, answer: str) -> Path:
    """Append the Q&A to the local daily briefing markdown file.

    Mirrors the `## 追記:` block the /notion-import skill writes to the Notion
    page, so the local `briefing_<date>.md` stays in sync with Notion. The
    file is created (with its parent dir) if it does not exist yet, so a Q&A
    is never silently dropped for a date with no briefing run.

    ``date`` is already constrained to ``^\\d{4}-\\d{2}-\\d{2}$`` by
    ``ChatNotionImportBody``, so it cannot path-traverse out of BRIEFING_DIR.
    """
    target = BRIEFING_DIR / f"briefing_{date}.md"
    block = (
        f"\n\n---\n\n"
        f"## 追記: QA チャット ({date})\n\n"
        f"**Q:** {question}\n\n"
        f"{answer}\n"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(block)
    return target


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
    # The /notion-import skill currently authenticates via the Notion MCP server
    # (configured in ~/.claude.json), but Python fallbacks like notion-client
    # read these env vars directly. Forwarding them keeps the skill working
    # even if a future revision switches off MCP, and matches what the
    # interactive `claude` CLI sees in the operator's shell.
    env["NOTION_API_KEY"] = api_key
    env["NOTION_DATABASE_ID"] = database_id

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

    # Notion is the primary durable artifact; the local briefing mirror is
    # best-effort. A filesystem hiccup here must not fail an already-successful
    # Notion append, so we log and continue rather than raising.
    try:
        local_path = _append_to_local_briefing(body.date, body.question, body.answer)
        logger.info("appended Q&A to local briefing %s", local_path)
    except OSError as exc:
        logger.warning("failed to append Q&A to local briefing for %s: %s", body.date, exc)

    return ChatNotionImportResponse(url=url_match.group(0), summary=final_text.strip()[:500])
