"""In-memory store for briefing run jobs.

Phase 1 assumes a single uvicorn process, so a plain ``dict`` guarded by a
``threading.Lock`` is sufficient. Phase 2 (multi-worker deployment) would
need to swap this for Redis or similar — keep the API narrow so that swap
stays local.
"""
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal

JobStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class Job:
    job_id: str
    status: JobStatus
    dry_run: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_lock = threading.Lock()
_store: dict[str, Job] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(dry_run: bool = False) -> Job:
    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, status="pending", dry_run=dry_run)
    with _lock:
        _store[job_id] = job
    return job


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _store.get(job_id)


def mark_running(job_id: str) -> Job | None:
    with _lock:
        job = _store.get(job_id)
        if not job:
            return None
        job.status = "running"
        job.started_at = _now_iso()
        return job


def mark_done(job_id: str) -> Job | None:
    with _lock:
        job = _store.get(job_id)
        if not job:
            return None
        job.status = "done"
        job.finished_at = _now_iso()
        return job


def mark_failed(job_id: str, error: str) -> Job | None:
    with _lock:
        job = _store.get(job_id)
        if not job:
            return None
        job.status = "failed"
        job.finished_at = _now_iso()
        job.error = error
        return job


def _reset_for_tests() -> None:
    """Test-only: clear the store so individual tests don't see each other's jobs."""
    with _lock:
        _store.clear()
