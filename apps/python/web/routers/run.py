"""POST /api/run + GET /api/run/{job_id} — async briefing execution.

Phase 1 design: a job is created in ``src.job_store`` (in-memory dict + lock),
``lambda_handler`` runs via ``BackgroundTasks`` so the POST returns 202
immediately. The frontend polls GET until status transitions to ``done`` /
``failed``.

``dry_run=true`` propagates to ``lambda_handler(dry_run=True)`` which runs
the credential preflight and returns without touching claude / Discord /
Notion — useful as a UI "is everything wired up?" check.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from src import job_store
from web.auth import require_bearer

# NB: ``src.handler`` is imported lazily inside ``_execute_briefing`` rather than
# at module top. ``src.handler`` does ``from src.config import CONFIG`` which
# triggers ``src.config.__getattr__('CONFIG')`` → ``load_config()`` →
# ``briefing.json`` read. Eager-importing here would defeat the lazy-config fix
# from #60 and crash ``./bin/serve.sh`` when ``briefing.json`` doesn't exist
# yet — the very file ``/api/config`` is supposed to let the operator create.

router = APIRouter(dependencies=[Depends(require_bearer)])


class RunResponse(BaseModel):
    job_id: str
    status: str


class JobDetail(BaseModel):
    job_id: str
    status: str
    dry_run: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


def _execute_briefing(job_id: str, dry_run: bool) -> None:
    """BackgroundTasks entrypoint. Always advances the job through
    running → done/failed regardless of exception path."""
    from src.handler import lambda_handler  # lazy — see module note

    job_store.mark_running(job_id)
    try:
        lambda_handler(dry_run=dry_run)
        job_store.mark_done(job_id)
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


@router.post("/run", status_code=202, response_model=RunResponse)
def post_run(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(default=False),
) -> RunResponse:
    job = job_store.create_job(dry_run=dry_run)
    background_tasks.add_task(_execute_briefing, job.job_id, dry_run)
    return RunResponse(job_id=job.job_id, status=job.status)


@router.get("/run/{job_id}", response_model=JobDetail)
def get_run(job_id: str) -> JobDetail:
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return JobDetail(**job.to_dict())
