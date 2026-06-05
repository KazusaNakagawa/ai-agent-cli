"""In-memory store for Q&A chat background jobs.

Mirrors ``src.job_store`` for briefing runs but with chat-specific fields:

- ``events``: bounded ring buffer of SSE-encoded bytes so a re-attaching
  client can replay everything since the subprocess started (needed to
  survive tab switches and page reloads — see #112 / #126).
- ``process``: the live ``subprocess.Popen`` handle so the cancel and
  grace-timeout paths can reach it.

Phase 1 single-process assumption matches ``src.job_store``; swap for
Redis-class storage when going multi-worker.
"""
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.job_store import JobStatus

# Caps the replay buffer per job. ~1000 SSE events covers a long answer
# (thousands of tokens at one line per event) while bounding memory.
DEFAULT_EVENT_BUFFER_MAX = 1000


@dataclass
class ChatJob:
    job_id: str
    status: JobStatus
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    # Each event is tagged with a monotonic seq id (starts at 1) so a
    # re-attaching client can identify "what's new" by filtering on
    # ``seq > last_seen_seq`` — robust against the deque trimming oldest
    # entries when the buffer hits its cap.
    events: deque[tuple[int, bytes]] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_EVENT_BUFFER_MAX),
    )
    process: subprocess.Popen | None = None
    _next_seq: int = 1


_lock = threading.Lock()
_store: dict[str, ChatJob] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job() -> ChatJob:
    job_id = str(uuid.uuid4())
    job = ChatJob(job_id=job_id, status="pending")
    with _lock:
        _store[job_id] = job
    return job


def get_job(job_id: str) -> ChatJob | None:
    with _lock:
        return _store.get(job_id)


def mark_running(job_id: str) -> ChatJob | None:
    with _lock:
        job = _store.get(job_id)
        if not job:
            return None
        job.status = "running"
        job.started_at = _now_iso()
        return job


def mark_done(job_id: str) -> ChatJob | None:
    with _lock:
        job = _store.get(job_id)
        if not job:
            return None
        job.status = "done"
        job.finished_at = _now_iso()
        return job


def mark_failed(job_id: str, error: str) -> ChatJob | None:
    with _lock:
        job = _store.get(job_id)
        if not job:
            return None
        job.status = "failed"
        job.finished_at = _now_iso()
        job.error = error
        return job


def snapshot_events_since(
    job_id: str, last_seq: int
) -> tuple[list[tuple[int, bytes]], JobStatus | None]:
    """Atomically snapshot events newer than ``last_seq`` plus the job status.

    Returns ``(new_events, status)``. ``status`` is ``None`` when the job has
    been GC'd. Taking the snapshot under the store lock prevents the caller
    from iterating ``events`` while the runner thread's ``append_event`` is
    mid-trim — without this, a ``deque`` at ``maxlen`` could raise
    ``RuntimeError: deque mutated during iteration``.
    """
    with _lock:
        job = _store.get(job_id)
        if job is None:
            return [], None
        new_events = [(seq, ev) for seq, ev in job.events if seq > last_seq]
        return new_events, job.status


def append_event(job_id: str, event: bytes) -> int | None:
    """Append an SSE-encoded event to the job's replay buffer.

    Returns the assigned monotonic seq id if the job existed (event was
    buffered) or ``None`` if the job is unknown (event dropped). The bounded
    ``deque`` silently trims the oldest entry when the cap is reached.
    """
    with _lock:
        job = _store.get(job_id)
        if not job:
            return None
        seq = job._next_seq
        job._next_seq += 1
        job.events.append((seq, event))
        return seq


def attach_process(job_id: str, process: subprocess.Popen) -> None:
    """Record the subprocess handle so cancel / grace-timeout can reach it.

    Silent no-op if the job is already missing (already GC'd)."""
    with _lock:
        job = _store.get(job_id)
        if job is not None:
            job.process = process


def detach_process(job_id: str) -> None:
    """Clear the subprocess handle once the process has exited.

    The events buffer is intentionally preserved so a late-attaching client
    can still replay the full transcript."""
    with _lock:
        job = _store.get(job_id)
        if job is not None:
            job.process = None


def remove_job(job_id: str) -> ChatJob | None:
    """Drop the job from the store.

    The caller is responsible for terminating the subprocess if one is
    still attached — we keep that explicit so callers don't hold the
    store lock across a slow ``terminate()``/``wait()``.
    """
    with _lock:
        return _store.pop(job_id, None)


def _reset_for_tests() -> None:
    """Test-only: clear the store so individual tests don't see each other's jobs."""
    with _lock:
        _store.clear()
