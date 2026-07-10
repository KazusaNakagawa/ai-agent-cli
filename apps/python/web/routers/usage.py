"""GET /api/usage — トークン使用量ログ (log/usage/*.jsonl) の閲覧 API。

ダッシュボード (Config > Usage) が日別の生レコードを取得して棒グラフに描画する。
書き込み側は ``src.usage_logger``、CLI 集計は ``src.usage_report`` と同じ
ファイル名規約 (``YYYYMMDD-usage.jsonl``) を共有する。
"""
import datetime
import json
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError

from src import usage_monitor
from src.usage_logger import USAGE_DIR, parse_usage_file_date
from src.usage_report import build_summary
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


class UsageDailySummary(BaseModel):
    """1 日分の全 run を合算した集計 (折れ線グラフ用)。"""

    date: str  # ISO ``YYYY-MM-DD``
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float


class UsageSummaryResponse(BaseModel):
    summary: list[UsageDailySummary]


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


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def get_summary() -> UsageSummaryResponse:
    """日別の全 run 合算を古い順 (時系列) で返す。

    ``usage_report.build_summary`` は ``(day, label)`` 単位なので、ここで
    ``day`` 単位に畳み込み直す。
    """
    if not USAGE_DIR.exists():
        return UsageSummaryResponse(summary=[])

    per_day: dict[str, UsageDailySummary] = {}
    for (day, _label), agg in build_summary(USAGE_DIR, days=None).items():
        entry = per_day.get(day)
        if entry is None:
            entry = UsageDailySummary(
                date=day,
                calls=0,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                cost_usd=0.0,
            )
            per_day[day] = entry
        entry.calls += agg["calls"]
        entry.input_tokens += agg["input_tokens"]
        entry.output_tokens += agg["output_tokens"]
        entry.cache_read_tokens += agg["cache_read_tokens"]
        entry.cache_creation_tokens += agg["cache_creation_tokens"]
        entry.cost_usd += agg["cost_usd"]

    summary = sorted(per_day.values(), key=lambda s: s.date)
    return UsageSummaryResponse(summary=summary)


class MonitorBucket(BaseModel):
    """One aggregation bucket (project, date, or model)."""

    key: str
    tokens: int
    cost_usd: float


class MonitorDateEntry(BaseModel):
    """One day's totals with per-model splits for stacked charts."""

    date: str  # ISO ``YYYY-MM-DD``
    tokens: int
    cost_usd: float
    models: list[MonitorBucket]


class MonitorResponse(BaseModel):
    total_tokens: int
    total_cost_usd: float
    by_project: list[MonitorBucket]
    by_date: list[MonitorDateEntry]
    by_model: list[MonitorBucket]
    unpriced_models: list[str]


_ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

# Aggregation walks the whole transcript tree, so identical queries within
# a short window are served from this in-process cache instead of rescanning.
# Bounded: distinct query ranges each occupy a slot, so evict the oldest
# entry once the cap is reached.
_MONITOR_CACHE_TTL_SECONDS = 60.0
_MONITOR_CACHE_MAX_ENTRIES = 32
_monitor_cache: dict[tuple[str, str | None, str | None], tuple[float, "MonitorResponse"]] = {}
# ``def`` endpoints run in FastAPI's threadpool, so concurrent requests can
# read/write _monitor_cache from different threads at once. Guard it.
_monitor_cache_lock = threading.Lock()


@router.get("/usage/monitor", response_model=MonitorResponse)
def get_monitor(
    since: str | None = Query(None, pattern=_ISO_DATE_PATTERN, description="YYYY-MM-DD"),
    until: str | None = Query(None, pattern=_ISO_DATE_PATTERN, description="YYYY-MM-DD"),
) -> MonitorResponse:
    """All-traffic token usage across Claude Code transcripts.

    Separate data source from ``/api/usage`` (app-run costs): this scans
    every transcript under ``~/.claude/projects/``. Costs are
    API-equivalent estimates, not actual billing.
    """
    # The Query pattern only checks shape; reject impossible calendar dates
    # (e.g. 2026-13-40) before they silently filter out everything.
    for name, value in (("since", since), ("until", until)):
        if value is not None:
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail=f"{name} is not a valid calendar date: {value}"
                )

    root = usage_monitor.DEFAULT_ROOT
    cache_key = (str(root), since, until)
    with _monitor_cache_lock:
        cached = _monitor_cache.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] < _MONITOR_CACHE_TTL_SECONDS:
            return cached[1]

    report = usage_monitor.aggregate(root, since=since, until=until)

    def _buckets(m: dict[str, usage_monitor.Bucket]) -> list[MonitorBucket]:
        return [
            MonitorBucket(key=k, tokens=b.tokens, cost_usd=b.cost)
            for k, b in sorted(m.items(), key=lambda kv: -kv[1].cost)
        ]

    by_date = [
        MonitorDateEntry(
            date=date,
            tokens=bucket.tokens,
            cost_usd=bucket.cost,
            models=_buckets(report.by_date_model.get(date, {})),
        )
        for date, bucket in sorted(report.by_date.items())
    ]
    response = MonitorResponse(
        total_tokens=report.total_tokens,
        total_cost_usd=report.total_cost,
        by_project=_buckets(report.by_project),
        by_date=by_date,
        by_model=_buckets(report.by_model),
        unpriced_models=sorted(report.unpriced_models),
    )
    with _monitor_cache_lock:
        if cache_key not in _monitor_cache and len(_monitor_cache) >= _MONITOR_CACHE_MAX_ENTRIES:
            oldest_key = min(_monitor_cache, key=lambda k: _monitor_cache[k][0])
            del _monitor_cache[oldest_key]
        _monitor_cache[cache_key] = (time.monotonic(), response)
    return response


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
