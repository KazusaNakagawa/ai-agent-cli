"""GET /api/export — download output/ and input/ trees as a single zip.

Bundles ``apps/python/output`` and ``apps/python/input`` into an in-memory zip
and streams it back as an attachment so the operator can move all generated and
input data to another machine in one click. Noise that isn't user data is
skipped: ``.DS_Store`` files and the ``.sessions`` dirs that hold internal
claude session ids.
"""
import io
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

_BASE = Path(__file__).parents[2]
OUTPUT_DIR = _BASE / "output"
INPUT_DIR = _BASE / "input"

# Names skipped anywhere in the tree: macOS cruft + internal session state.
_EXCLUDED_NAMES = {".DS_Store", ".sessions"}


def _add_dir(zf: zipfile.ZipFile, root: Path) -> None:
    """Add every file under ``root`` to ``zf``, keeping paths relative to its parent."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _EXCLUDED_NAMES & set(path.relative_to(root).parts):
            continue
        zf.write(path, arcname=path.relative_to(root.parent))


def _build_zip(roots: list[Path]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root in roots:
            _add_dir(zf, root)
    return buf.getvalue()


@router.get("/export")
def get_export() -> StreamingResponse:
    """Return the output/ and input/ trees as a downloadable zip attachment."""
    data = _build_zip([OUTPUT_DIR, INPUT_DIR])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"archive-{stamp}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
