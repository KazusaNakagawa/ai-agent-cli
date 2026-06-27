"""GET /api/export — download the whole output/ tree as a single zip.

Bundles ``apps/python/output`` (briefing, journal, eval, archive, ...) into an
in-memory zip and streams it back as an attachment so the operator can move
all generated data to another machine in one click. Noise that isn't user
data is skipped: ``.DS_Store`` files and the ``.sessions`` dirs that hold
internal claude session ids.
"""
import io
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

OUTPUT_DIR = Path(__file__).parents[2] / "output"

# Names skipped anywhere in the tree: macOS cruft + internal session state.
_EXCLUDED_NAMES = {".DS_Store", ".sessions"}


def _build_zip(root: Path) -> bytes:
    """Zip every file under ``root``, keeping paths relative to its parent."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if root.exists():
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                # Skip if any path segment is excluded (covers .sessions dirs).
                if _EXCLUDED_NAMES & set(path.relative_to(root).parts):
                    continue
                zf.write(path, arcname=path.relative_to(root.parent))
    return buf.getvalue()


@router.get("/export")
def get_export() -> StreamingResponse:
    """Return the output/ tree as a downloadable zip attachment."""
    data = _build_zip(OUTPUT_DIR)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"archive-{stamp}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
