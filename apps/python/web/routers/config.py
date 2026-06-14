"""GET / PUT /api/config — briefing.json の読み書き。

PUT は disk に書き込むだけで、起動中プロセスの ``src.config.CONFIG`` グローバル
（import 時に ``load_config()`` 実行）はリロードしない。Phase 1 のブリーフィング
は cron から ``bin/run.sh`` 経由で別 Python プロセスを起こすので、PUT は次回
batch 実行時に自動で反映される。リアルタイム反映が必要になったら、ここで
``CONFIG`` を更新するか、別途リロード用エンドポイントを足す方針。
"""
import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from web.auth import require_bearer
from web.schemas import BriefingConfigSchema

router = APIRouter(dependencies=[Depends(require_bearer)])


def _config_path() -> Path:
    return Path(
        os.getenv(
            "BRIEFING_CONFIG_PATH",
            str(Path(__file__).resolve().parents[2] / "config" / "briefing.json"),
        )
    )


@router.get("/config", response_model=BriefingConfigSchema)
def get_config() -> BriefingConfigSchema:
    path = _config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="briefing.json not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail="briefing.json is corrupt") from e
    try:
        return BriefingConfigSchema.model_validate(data)
    except ValidationError as e:
        raise HTTPException(
            status_code=500,
            detail="briefing.json does not match the expected schema",
        ) from e


@router.put("/config")
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
