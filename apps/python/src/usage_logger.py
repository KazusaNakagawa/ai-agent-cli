"""Claude CLI 呼び出しごとのトークン使用量・コストを JSONL に追記する。

`src/logger.py` の「日次ファイル + 7 日リテンション」規約に倣う。
ログ記録の失敗が元のタスクを壊してはならないため、例外は握りつぶす。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from src.constants import LOG_RETENTION_DAYS
from src.logger import get_logger

logger = get_logger(__name__)

USAGE_DIR = Path(__file__).parents[1] / "log" / "usage"


def _purge_old_logs(usage_dir: Path) -> None:
    cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    for path in usage_dir.glob("*-usage.jsonl"):
        try:
            file_date = datetime.strptime(path.stem.replace("-usage", ""), "%Y%m%d")
            if file_date.date() < cutoff.date():
                path.unlink()
        except (ValueError, OSError):
            pass


def log_usage(label: str, usage: dict, cost_usd: float | None, duration_ms: int | None) -> None:
    """1 回の claude 呼び出しの使用量を当日ファイルに 1 行追記する。

    例外は記録のみで握りつぶす — 使用量ログの失敗で本処理を止めない。
    """
    try:
        USAGE_DIR.mkdir(parents=True, exist_ok=True)
        _purge_old_logs(USAGE_DIR)

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
    except Exception:  # noqa: BLE001 — 使用量ログの失敗は本処理を止めない
        logger.warning("使用量ログの記録に失敗しました [%s]", label, exc_info=True)
