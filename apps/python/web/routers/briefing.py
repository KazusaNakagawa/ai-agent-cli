"""GET /api/briefing — list and read apps/python/output/briefing/*.md.

The briefing viewer (Sidebar > Briefing) fetches the file list to render the
record list, then fetches the selected file's Markdown body.

Filename convention: ``{type}_{YYYY-MM-DD}[-NNN].md``
``type`` is any lowercase-led prefix (``briefing`` / ``local`` / ``market`` ...).
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

BRIEFING_DIR = Path(__file__).parents[2] / "output" / "briefing"

# filename: <type>_YYYY-MM-DD[-NNN].md — type is any lowercase-led prefix.
_FILE_RE = re.compile(r"^([a-z][\w-]*?)_(\d{4}-\d{2}-\d{2})(?:-\d+)?\.md$")
# safe-name guard: only alphanum / underscore / hyphen + .md — no path separators
_SAFE_NAME_RE = re.compile(r"^[\w-]+\.md$")


class BriefingFile(BaseModel):
    name: str
    type: str
    date: str  # YYYY-MM-DD
    size: int  # bytes


class BriefingListResponse(BaseModel):
    files: list[BriefingFile]


class BriefingFileResponse(BaseModel):
    name: str
    content: str


@router.get("/briefing", response_model=BriefingListResponse)
def list_briefings() -> BriefingListResponse:
    """Return available briefing files, newest first."""
    return BriefingListResponse(files=_scan_files())


def _scan_files() -> list[BriefingFile]:
    """Return convention-matching md files in BRIEFING_DIR, newest first (date, name DESC)."""
    if not BRIEFING_DIR.exists():
        return []

    files: list[BriefingFile] = []
    for path in BRIEFING_DIR.glob("*.md"):
        if not path.is_file():
            continue
        m = _FILE_RE.match(path.name)
        if m is None:
            continue
        files.append(
            BriefingFile(
                name=path.name,
                type=m.group(1),
                date=m.group(2),
                size=path.stat().st_size,
            )
        )
    files.sort(key=lambda f: (f.date, f.name), reverse=True)
    return files


@router.get("/briefing/search", response_model=BriefingListResponse)
def search_briefings(q: str = "") -> BriefingListResponse:
    """Return files whose name or body contains ``q`` (case-insensitive, substring), newest first.

    An empty query returns all files. Must be registered before ``/briefing/{name}``.
    """
    needle = q.strip().lower()
    files = _scan_files()
    if not needle:
        return BriefingListResponse(files=files)

    matched: list[BriefingFile] = []
    for f in files:
        if needle in f.name.lower():
            matched.append(f)
            continue
        body = (BRIEFING_DIR / f.name).read_text(encoding="utf-8")
        if needle in body.lower():
            matched.append(f)
    return BriefingListResponse(files=matched)


@router.get("/briefing/{name}", response_model=BriefingFileResponse)
def get_briefing(name: str) -> BriefingFileResponse:
    """Return the Markdown body of the named file. Invalid names or paths outside the dir 404."""
    if not _SAFE_NAME_RE.match(name) or _FILE_RE.match(name) is None:
        raise HTTPException(status_code=404, detail=f"Briefing not found: {name}")

    path = BRIEFING_DIR / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Briefing not found: {name}")

    return BriefingFileResponse(name=name, content=path.read_text(encoding="utf-8"))
