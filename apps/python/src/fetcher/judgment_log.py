"""Read judgment-loop log entries for self-agent, tracking a watermark."""
from __future__ import annotations

import json
import pathlib

from src.logger import get_logger

logger = get_logger(__name__)

DEFAULT_JUDGMENT_LOOP_DIR = pathlib.Path.home() / ".local" / "share" / "judgment-loop"
WATERMARK_FILENAME = ".self-agent-watermark"


def _resolve_dir(judgment_loop_dir: pathlib.Path | None) -> pathlib.Path:
    return judgment_loop_dir or DEFAULT_JUDGMENT_LOOP_DIR


def read_watermark(judgment_loop_dir: pathlib.Path | None = None) -> str | None:
    """Return the last processed log id, or None if no watermark exists yet."""
    path = _resolve_dir(judgment_loop_dir) / WATERMARK_FILENAME
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def write_watermark(last_id: str, judgment_loop_dir: pathlib.Path | None = None) -> None:
    """Persist the id of the most recently processed log entry."""
    path = _resolve_dir(judgment_loop_dir) / WATERMARK_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(last_id, encoding="utf-8")


def fetch_new_entries(judgment_loop_dir: pathlib.Path | None = None) -> list[dict]:
    """Return judgment-log entries newer than the stored watermark.

    A missing or empty judgments.jsonl yields an empty list rather than
    raising, since "no logs yet" is a normal state, not an error. If the
    watermark id no longer appears in the log (e.g. it was manually pruned),
    all entries are returned and a warning is logged rather than silently
    dropping evidence.
    """
    dir_ = _resolve_dir(judgment_loop_dir)
    log_path = dir_ / "judgments.jsonl"
    if not log_path.exists():
        return []

    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    entries = [json.loads(line) for line in lines]

    watermark = read_watermark(dir_)
    if watermark is None:
        return entries

    for i, entry in enumerate(entries):
        if entry.get("id") == watermark:
            return entries[i + 1 :]

    logger.warning(
        "watermark id %r not found in judgment log; processing all entries", watermark
    )
    return entries
