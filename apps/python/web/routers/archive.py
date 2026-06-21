"""POST /api/archive — run the monthly briefing archive script.

Invokes ``apps/python/bin/archive.sh`` via subprocess. The target month is
optional and defaults to the previous month (decided by the script). On a
non-zero exit the endpoint returns 500 with an excerpt of stderr.
"""
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

ARCHIVE_SCRIPT = Path(__file__).parents[2] / "bin" / "archive.sh"
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_STDERR_EXCERPT = 2000


class ArchiveResponse(BaseModel):
    exit_code: int
    stdout: str


@router.post("/archive", response_model=ArchiveResponse)
def post_archive(
    month: str | None = Query(default=None, description="Target month YYYY-MM (default: previous)"),
    prune: bool = Query(default=False),
) -> ArchiveResponse:
    if month is not None and not _MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail=f"month must be YYYY-MM, got: {month}")

    cmd = [str(ARCHIVE_SCRIPT)]
    if month is not None:
        cmd += ["--month", month]
    if prune:
        cmd.append("--prune")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        excerpt = result.stderr.strip()[-_STDERR_EXCERPT:]
        raise HTTPException(
            status_code=500,
            detail=f"archive failed (exit {result.returncode}): {excerpt}",
        )
    return ArchiveResponse(exit_code=result.returncode, stdout=result.stdout)
