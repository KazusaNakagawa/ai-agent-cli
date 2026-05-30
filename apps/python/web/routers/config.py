"""GET / PUT /api/config — briefing.json の読み書き。"""
import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from web.auth import require_bearer
from web.schemas import BriefingConfigSchema

router = APIRouter()


def _config_path() -> Path:
    return Path(
        os.getenv(
            "BRIEFING_CONFIG_PATH",
            str(Path(__file__).resolve().parents[2] / "config" / "briefing.json"),
        )
    )


@router.get("/config", dependencies=[Depends(require_bearer)])
def get_config() -> dict:
    path = _config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="briefing.json not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.put("/config", dependencies=[Depends(require_bearer)])
def put_config(payload: BriefingConfigSchema) -> dict:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload.model_dump(mode="json")
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
    return data
