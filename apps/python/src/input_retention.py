"""Delete raw inputs once they have been processed (#605, policy in #598).

Two kinds of raw input pile up under ``input/``:

* **Bank statements** (``input/money/*.csv``). After a real import the ledger
  holds every row, ``desc_raw`` included, and re-importing is a no-op for rows
  already stored, so the CSV is a redundant plaintext copy. Recovery is to
  download it from the bank again. Each import is recorded with the file's
  hash; a file is deleted only when that hash still matches, so a re-downloaded
  or edited file is never removed early. Hand-transcribed ``manual`` files have
  no upstream and are never deleted, and nothing outside ``input/`` is touched.
* **Chat/journal uploads** (``input/images/YYYY-MM-DD/``,
  ``input/attachments/YYYY-MM-DD/``). Most are read once when a message is
  sent, but saved journal entries link to some of them, so a file is deleted
  only when nothing under ``output/`` references its ``/api/<kind>/...`` URL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from src.private_files import write_private_text

logger = logging.getLogger(__name__)

# Parsers whose files have no upstream copy to re-download.
KEEP_PARSERS = frozenset({"manual"})
UPLOAD_KINDS = ("images", "attachments")
# Text files under output/ that can hold a link to an upload.
_REFERENCE_SUFFIXES = frozenset({".md", ".json", ".jsonl", ".txt"})
_UPLOAD_URL_RE = re.compile(r"/api/(?:images|attachments)/\d{4}-\d{2}-\d{2}/[^\s)\"'<>\]]+")


@dataclass
class PruneResult:
    deleted: list[Path] = field(default_factory=list)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    entries = []
    for number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if not all(isinstance(entry.get(k), str) for k in ("path", "parser", "sha256")):
                raise ValueError("missing field")
            datetime.fromisoformat(entry["imported_at"])
        except (ValueError, KeyError, TypeError, AttributeError):
            logger.warning("%s:%d: unreadable import record skipped", log_path, number)
            continue
        entries.append(entry)
    return entries


def _save_log(log_path: Path, entries: list[dict]) -> None:
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    write_private_text(log_path, text)


def record_imports(log_path: Path, files: list[tuple[Path, str]], *, now: datetime) -> None:
    """Record ``(path, parser)`` pairs as imported at ``now``; a re-import resets the clock."""
    entries = {e["path"]: e for e in _load_log(log_path)}
    for path, parser in files:
        resolved = path.resolve()
        entries[str(resolved)] = {
            "path": str(resolved),
            "parser": parser,
            "sha256": _sha256(resolved),
            "imported_at": now.isoformat(timespec="seconds"),
        }
    _save_log(log_path, list(entries.values()))


def _prune_statements(
    input_dir: Path, log_path: Path, cutoff: datetime, dry_run: bool
) -> list[Path]:
    root = input_dir.resolve()
    deleted: list[Path] = []
    remaining: list[dict] = []
    for entry in _load_log(log_path):
        path = Path(entry["path"])
        if not path.is_file():
            continue  # already gone: forget it
        due = (
            entry["parser"] not in KEEP_PARSERS
            and path.is_relative_to(root)
            and datetime.fromisoformat(entry["imported_at"]) < cutoff
            and _sha256(path) == entry["sha256"]
        )
        if not due:
            remaining.append(entry)
            continue
        deleted.append(path)
        if not dry_run:
            path.unlink()
            logger.info("deleted imported statement %s", path)
    if not dry_run and log_path.exists():
        _save_log(log_path, remaining)
    return deleted


def _referenced_urls(output_dir: Path) -> set[str]:
    found: set[str] = set()
    if not output_dir.is_dir():
        return found
    for path in output_dir.rglob("*"):
        if path.suffix not in _REFERENCE_SUFFIXES or not path.is_file():
            continue
        try:
            found.update(_UPLOAD_URL_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return found


def _prune_uploads(
    input_dir: Path, output_dir: Path, cutoff_day: date, dry_run: bool
) -> list[Path]:
    referenced: set[str] | None = None  # scanned lazily: most runs find nothing old
    deleted: list[Path] = []
    for kind in UPLOAD_KINDS:
        base = input_dir / kind
        if not base.is_dir():
            continue
        for day_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            try:
                day = date.fromisoformat(day_dir.name)
            except ValueError:
                continue  # not one of ours
            if day >= cutoff_day:
                continue
            if referenced is None:
                referenced = _referenced_urls(output_dir)
            for path in sorted(p for p in day_dir.iterdir() if p.is_file()):
                if f"/api/{kind}/{day_dir.name}/{path.name}" in referenced:
                    continue
                deleted.append(path)
                if not dry_run:
                    path.unlink()
                    logger.info("deleted unreferenced upload %s", path)
            if not dry_run and not any(day_dir.iterdir()):
                day_dir.rmdir()
    return deleted


def prune(
    *,
    input_dir: Path,
    output_dir: Path,
    import_log: Path,
    now: datetime,
    retention_days: int,
    dry_run: bool = False,
) -> PruneResult:
    """Delete processed inputs older than ``retention_days``; see the module docstring."""
    cutoff = now - timedelta(days=retention_days)
    result = PruneResult()
    result.deleted += _prune_statements(input_dir, import_log, cutoff, dry_run)
    result.deleted += _prune_uploads(input_dir, output_dir, cutoff.date(), dry_run)
    return result

