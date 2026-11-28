"""POST /api/archive — run the monthly briefing archive script.

Invokes ``apps/python/bin/archive.sh`` via subprocess. The target month is
optional and defaults to the previous month (decided by the script). On success
the response carries a structured summary (month, file count, a short message)
next to the raw script output, which is also written to the server log so the UI
can show the summary alone. On a non-zero exit the endpoint returns 500 with an
excerpt of stderr.
"""
import os
import re
import subprocess
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src import paths
from src.logger import get_logger
from web.auth import require_bearer

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_bearer)])

ARCHIVE_SCRIPT = paths.BIN_DIR / "archive.sh"
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_STDERR_EXCERPT = 2000

# Lines archive.sh prints (see apps/python/bin/archive.sh). Anchored to line
# starts so the per-file ``adding: ...`` noise from zip can never match.
_CREATED_RE = re.compile(r"^created: .*briefing_(\d{4}-\d{2})\.zip \((\d+) files?\)\s*$", re.MULTILINE)
_SKIPPED_RE = re.compile(r"^skip: no briefing files for (\d{4}-\d{2}) ", re.MULTILINE)
_PRUNED_RE = re.compile(r"^pruned: (\d+) local md files", re.MULTILINE)


class ArchiveResponse(BaseModel):
    exit_code: int
    # Raw script output, kept for debugging; the UI shows ``message`` instead.
    stdout: str
    # ``unknown`` means the script succeeded but its output was not recognised.
    status: Literal["archived", "skipped", "unknown"]
    month: str | None = None
    file_count: int | None = None
    pruned: bool = False
    message: str


def summarize_archive_output(stdout: str) -> dict:
    """Turn archive.sh's output into the structured part of the response."""
    created = _CREATED_RE.search(stdout)
    if created:
        month, count = created.group(1), int(created.group(2))
        pruned = _PRUNED_RE.search(stdout) is not None
        noun = "file" if count == 1 else "files"
        suffix = ", local copies removed" if pruned else ""
        return {
            "status": "archived",
            "month": month,
            "file_count": count,
            "pruned": pruned,
            "message": f"Archived {month} ({count} {noun}{suffix})",
        }
    skipped = _SKIPPED_RE.search(stdout)
    if skipped:
        month = skipped.group(1)
        return {
            "status": "skipped",
            "month": month,
            "file_count": 0,
            "pruned": False,
            "message": f"Nothing to archive for {month}: no briefing files.",
        }
    return {"status": "unknown", "message": "Archive complete."}


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

    # No command injection: args are passed as a list (no shell=True), the only
    # dynamic value (month) is regex-validated to ^\d{4}-\d{2}$ above, and the
    # binary path is a fixed constant.
    # archive.sh defaults to repo-relative dirs; pass the resolved data-home
    # dirs so a relocated install (BRIEF_LENS_HOME) archives the right files.
    env = {
        **os.environ,
        "ARCHIVE_BRIEFING_DIR": str(paths.OUTPUT_DIR / "briefing"),
        "ARCHIVE_OUTPUT_DIR": str(paths.OUTPUT_DIR / "archive"),
    }
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)  # noqa: S603
    if result.returncode != 0:
        excerpt = result.stderr.strip()[-_STDERR_EXCERPT:]
        raise HTTPException(
            status_code=500,
            detail=f"archive failed (exit {result.returncode}): {excerpt}",
        )
    logger.info("archive.sh output (exit %d):\n%s", result.returncode, result.stdout.rstrip())
    return ArchiveResponse(exit_code=result.returncode, stdout=result.stdout, **summarize_archive_output(result.stdout))
