"""GET /api/briefing — apps/python/output/briefing/*.md のリスト・内容取得 API。

ブリーフィングビューア (Sidebar > Briefing) がファイル一覧を取得して
一覧表示し、選択されたファイルの Markdown 本文を返す。

ファイル名規約: ``{type}_{YYYY-MM-DD}[-NNN].md``
type は ``briefing`` または ``local`` の 2 種。
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

BRIEFING_DIR = Path(__file__).parents[2] / "output" / "briefing"

# filename: briefing_YYYY-MM-DD[-NNN].md  or  local_YYYY-MM-DD[-NNN].md
_FILE_RE = re.compile(r"^(briefing|local)_(\d{4}-\d{2}-\d{2})(?:-\d+)?\.md$")
# safe-name guard: only alphanum / underscore / hyphen + .md — no path separators
_SAFE_NAME_RE = re.compile(r"^[\w-]+\.md$")


class BriefingFile(BaseModel):
    name: str
    type: str  # "briefing" | "local"
    date: str  # YYYY-MM-DD
    size: int  # bytes


class BriefingListResponse(BaseModel):
    files: list[BriefingFile]


class BriefingFileResponse(BaseModel):
    name: str
    content: str


@router.get("/briefing", response_model=BriefingListResponse)
def list_briefings() -> BriefingListResponse:
    """利用可能なブリーフィングファイルを新しい順で返す。"""
    if not BRIEFING_DIR.exists():
        return BriefingListResponse(files=[])

    files: list[BriefingFile] = []
    for path in BRIEFING_DIR.glob("*.md"):
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
    return BriefingListResponse(files=files)


@router.get("/briefing/{name}", response_model=BriefingFileResponse)
def get_briefing(name: str) -> BriefingFileResponse:
    """指定ファイルの Markdown 本文を返す。不正名やディレクトリ外は 404。"""
    if not _SAFE_NAME_RE.match(name) or _FILE_RE.match(name) is None:
        raise HTTPException(status_code=404, detail=f"Briefing not found: {name}")

    path = BRIEFING_DIR / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Briefing not found: {name}")

    return BriefingFileResponse(name=name, content=path.read_text(encoding="utf-8"))
