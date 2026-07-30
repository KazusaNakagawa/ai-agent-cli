"""Append per-Claude-CLI-call token usage and cost to a JSONL file.

Follows the "one file per day" convention from `src/logger.py`, but retention is
opt-in: `USAGE_LOG_ROTATION_ENABLED` is False by default so the whole cost
history stays available to the Usage dashboard (#428).
Exceptions are swallowed because a logging failure must never break the
original task.
"""
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.constants import LOG_RETENTION_DAYS, USAGE_LOG_ROTATION_ENABLED
from src.logger import get_logger

logger = get_logger(__name__)

USAGE_DIR = Path(__file__).parents[1] / "log" / "usage"


USAGE_FILE_GLOB = "*-usage.jsonl"


def parse_usage_file_date(path: Path):
    """Extract the date from a ``YYYYMMDD-usage.jsonl`` filename.

    Shared by ``usage_logger`` and ``bin/usage_report.py`` to prevent drift in
    the filename convention. Returns ``None`` if it cannot be parsed.
    """
    try:
        return datetime.strptime(path.stem.replace("-usage", ""), "%Y%m%d").date()
    except ValueError:
        return None


_last_purge_date = None


def _maybe_purge(usage_dir: Path) -> None:
    """Call ``_purge_old_logs`` at most once per day to avoid duplicate purges.

    Avoids the waste of globbing the whole directory on every high-frequency call.
    Skipped entirely when ``USAGE_LOG_ROTATION_ENABLED`` is False (the default) —
    the once-per-day memo is still stamped so the debug line stays quiet.
    """
    global _last_purge_date
    today = datetime.now().date()
    if _last_purge_date == today:
        return
    _last_purge_date = today
    if not USAGE_LOG_ROTATION_ENABLED:
        logger.debug("usage log rotation disabled — keeping all daily usage files")
        return
    _purge_old_logs(usage_dir)


def _purge_old_logs(usage_dir: Path) -> None:
    cutoff = (datetime.now() - timedelta(days=LOG_RETENTION_DAYS)).date()
    for path in usage_dir.glob(USAGE_FILE_GLOB):
        file_date = parse_usage_file_date(path)
        if file_date is None:
            continue
        try:
            if file_date < cutoff:
                path.unlink()
        except OSError:
            pass


def log_usage(label: str, usage: dict, cost_usd: float | None, duration_ms: int | None) -> None:
    """Append one line of usage for a single claude call to today's file.

    Exceptions are logged and swallowed — a usage-log failure must not stop the
    main task.
    """
    try:
        USAGE_DIR.mkdir(parents=True, exist_ok=True)
        _maybe_purge(USAGE_DIR)

        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "label": label,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
            "cost_usd": cost_usd,
            "duration_ms": duration_ms,
        }

        log_file = USAGE_DIR / f"{datetime.now().strftime('%Y%m%d')}-usage.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — a usage-log failure must not stop the main task
        logger.warning("failed to record usage log [%s]", label, exc_info=True)


def log_usage_from_result(label: str, result_obj: Mapping[str, Any] | None) -> bool:
    """Log usage from a claude CLI ``result`` record (token-consuming call).

    ``result_obj`` is the parsed terminal object of a ``--output-format json``
    or ``--output-format stream-json`` run — it carries ``usage`` plus
    ``total_cost_usd`` / ``duration_ms``. This is the single entry point every
    cost-consuming call site should funnel through so the usage-log format
    stays uniform.

    Returns ``True`` when a usage record was logged, ``False`` when the object
    has no ``usage`` dict (a no-op the caller can branch on for debug logging).
    """
    usage = result_obj.get("usage") if result_obj is not None else None
    if not isinstance(usage, dict):
        logger.debug("no usage in result object, skipping usage log [%s]", label)
        return False
    log_usage(
        label=label,
        usage=usage,
        cost_usd=result_obj.get("total_cost_usd"),
        duration_ms=result_obj.get("duration_ms"),
    )
    return True
