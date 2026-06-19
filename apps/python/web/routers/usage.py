"""GET /api/usage — トークン使用量ログ (log/usage/*.jsonl) の閲覧 API。

ダッシュボード (Config > Usage) が日別の生レコードを取得して棒グラフに描画する。
書き込み側は ``src.usage_logger``、CLI 集計は ``src.usage_report`` と同じ
ファイル名規約 (``YYYYMMDD-usage.jsonl``) を共有する。
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError

from src.usage_logger import USAGE_DIR, parse_usage_file_date
from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

# 厳格な YYYYMMDD のみ許可。``..`` やパス区切りを含む入力を
# ファイルパス組み立て前に弾き、USAGE_DIR 外への脱出を防ぐ。
_DATE_RE = re.compile(r"^\d{8}$")


class UsageRecord(BaseModel):
    timestamp: str
    label: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None
    duration_ms: int | None = None


class UsageDatesResponse(BaseModel):
    dates: list[str]


class UsageDayResponse(BaseModel):
    date: str
    records: list[UsageRecord]


@router.get("/usage/dates", response_model=UsageDatesResponse)
def list_dates() -> UsageDatesResponse:
    """利用可能な ``YYYYMMDD`` を新しい順で返す。"""
    if not USAGE_DIR.exists():
        return UsageDatesResponse(dates=[])
    dates = []
    for path in USAGE_DIR.glob("*-usage.jsonl"):
        file_date = parse_usage_file_date(path)
        if file_date is not None:
            dates.append(file_date.strftime("%Y%m%d"))
    dates.sort(reverse=True)
    return UsageDatesResponse(dates=dates)


@router.get("/usage", response_model=UsageDayResponse)
def get_usage(date: str = Query(..., description="YYYYMMDD")) -> UsageDayResponse:
    """指定日の生レコードを配列で返す。存在しない / 不正な日付は 404。"""
    # パス組み立て前に厳格検証。不正な date はファイルに触れず 404。
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=404, detail=f"No usage log for date: {date}")

    log_file = USAGE_DIR / f"{date}-usage.jsonl"
    if parse_usage_file_date(log_file) is None or not log_file.exists():
        raise HTTPException(status_code=404, detail=f"No usage log for date: {date}")

    records: list[UsageRecord] = []
    with log_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # ValidationError は pydantic v2 で ValueError サブクラスだが、
            # 明示しておき将来の挙動変化にも備える。不正行は読み飛ばす。
            try:
                records.append(UsageRecord(**json.loads(line)))
            except (json.JSONDecodeError, ValidationError, ValueError):
                continue
    return UsageDayResponse(date=date, records=records)
