"""Journal store — one Markdown file per entry.

Each journal entry is a standalone Markdown file under ``JOURNAL_DIR`` named
``YYYY-MM-DD_HHMMSS.md`` (the file stem is the entry id). A single day can
therefore hold many independent entries, and an entry can be removed by
deleting its file.

Backward compatibility: legacy day-based files named ``YYYY-MM-DD.md`` (one
file per day from the previous append-only model) are still listed and
readable. Their entry id is the bare date. No one-shot migration is required —
old files are picked up on read, new entries use the per-entry naming.

``JOURNAL_DIR`` lives under ``output/`` which is gitignored, so personal
notes are never committed (matches the briefing output convention).
"""
import re
import threading
from datetime import datetime
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)

JOURNAL_DIR = Path(__file__).parents[1] / "output" / "journal"

# Serializes sidecar read-modify-write so concurrent save_item/save_notion_meta
# calls for the same entry can't clobber each other's update.
_SIDECAR_LOCK = threading.Lock()

# Entry id: a date, optionally followed by "_<suffix>" (time and/or collision
# counter). Legacy day files (bare "YYYY-MM-DD") match with no suffix.
_ENTRY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_[0-9A-Za-z-]+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today() -> str:
    """Return today's date as YYYY-MM-DD (local time)."""
    return datetime.now().strftime("%Y-%m-%d")


def _validate_date(value: str) -> None:
    """Raise ValueError unless value is a real calendar date (YYYY-MM-DD)."""
    if not _DATE_RE.match(value):
        raise ValueError(f"Invalid journal date: {value!r}")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid journal date: {value!r}") from exc


def date_of(entry_id: str) -> str:
    """Return the date (YYYY-MM-DD) embedded in an entry id."""
    m = _ENTRY_RE.match(entry_id)
    if not m:
        raise ValueError(f"Invalid journal entry id: {entry_id!r}")
    return m.group(1)


def _path_for(entry_id: str) -> Path:
    """Return the file path for an entry id, validating its format first."""
    if not _ENTRY_RE.match(entry_id):
        raise ValueError(f"Invalid journal entry id: {entry_id!r}")
    return JOURNAL_DIR / f"{entry_id}.md"


def _item_path(entry_id: str) -> Path:
    return JOURNAL_DIR / f"{entry_id}.json"


def _read_sidecar(path: Path) -> dict:
    import json

    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("failed to read journal sidecar at %s; treating as empty", path, exc_info=True)
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("failed to decode journal sidecar JSON at %s; treating as empty", path, exc_info=True)
        return {}


def _merge_sidecar(entry_id: str, updates: dict) -> None:
    """Merge ``updates`` into the entry's JSON sidecar, preserving other keys.

    ``item`` (short label) and ``notion_page_id`` (Notion sync) share this same
    file, so a write from one must not clobber a value written by the other.
    The read-modify-write is serialized by ``_SIDECAR_LOCK`` so concurrent
    updates (e.g. an item label saved while a background Notion sync writes
    the page id) can't race each other.
    """
    import json

    path = _item_path(entry_id)
    with _SIDECAR_LOCK:
        data = _read_sidecar(path)
        data.update(updates)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def save_item(entry_id: str, item: str) -> None:
    """Persist a short item label (≤20 chars) alongside the entry markdown."""
    if not _ENTRY_RE.match(entry_id):
        raise ValueError(f"Invalid journal entry id: {entry_id!r}")
    _merge_sidecar(entry_id, {"item": item[:20]})


def get_item(entry_id: str) -> str:
    """Return the stored item label for an active entry, or empty string if absent."""
    if not _ENTRY_RE.match(entry_id):
        return ""
    return _read_sidecar(_item_path(entry_id)).get("item", "")


def save_notion_meta(entry_id: str, page_id: str, url: str = "") -> None:
    """Persist the Notion page id (and page url, for UI display) for this entry."""
    if not _ENTRY_RE.match(entry_id):
        raise ValueError(f"Invalid journal entry id: {entry_id!r}")
    updates = {"notion_page_id": page_id}
    if url:
        updates["notion_url"] = url
    _merge_sidecar(entry_id, updates)


def get_notion_meta(entry_id: str) -> str:
    """Return the entry's synced Notion page id, or empty string if not yet synced."""
    if not _ENTRY_RE.match(entry_id):
        return ""
    return _read_sidecar(_item_path(entry_id)).get("notion_page_id", "")


def get_notion_url(entry_id: str) -> str:
    """Return the entry's synced Notion page URL, or empty string if not yet synced."""
    if not _ENTRY_RE.match(entry_id):
        return ""
    return _read_sidecar(_item_path(entry_id)).get("notion_url", "")


def get_trashed_item(entry_id: str) -> str:
    """Return the stored item label for a soft-deleted entry, or empty string."""
    import json

    if not _ENTRY_RE.match(entry_id):
        return ""
    p = _deleted_dir() / f"{entry_id}.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("item", "")
    except Exception:
        return ""


def append_entry(content: str, date: str | None = None) -> str:
    """Create a new entry file for the given date and return its entry id.

    Each call writes a distinct file named ``{date}_{HHMMSS}.md``; if that name
    is already taken (two entries within the same second), a ``-N`` counter is
    appended so no entry overwrites another.
    """
    text = content.strip()
    if not text:
        raise ValueError("Journal entry content must not be empty")

    date = date or today()
    _validate_date(date)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    base = f"{date}_{now.strftime('%H%M%S')}"
    timestamp = now.strftime("%H:%M:%S")
    body = f"# Journal {date}\n\n## {timestamp}\n\n{text}\n"

    # Exclusive create ("x") guarantees a fresh file; on collision bump the
    # counter and retry so concurrent appends within the same second don't
    # clobber each other.
    entry_id = base
    n = 1
    while True:
        try:
            with open(JOURNAL_DIR / f"{entry_id}.md", "x", encoding="utf-8") as fh:
                fh.write(body)
            return entry_id
        except FileExistsError:
            # Zero-pad so reverse-lexicographic listing keeps creation order
            # even past 9 entries in the same second (-000010 sorts after -000009).
            entry_id = f"{base}-{n:06d}"
            n += 1


def append_to_entry(entry_id: str, content: str) -> bool:
    """Append additional content to an existing entry file.

    Returns True if the entry was found and updated, False if it does not exist.
    Used when a brainstorm session continues: subsequent turns are appended to
    the same file rather than creating a new one.
    """
    text = content.strip()
    if not text:
        return False
    if not _ENTRY_RE.match(entry_id):
        return False
    path = JOURNAL_DIR / f"{entry_id}.md"
    if not path.exists() or not path.is_file():
        return False
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n\n---\n\n{text}\n")
    return True


def _list_entry_files(directory: Path) -> list[tuple[str, Path]]:
    """Return (entry_id, path) for entry files in a directory, newest first.

    Entry ids start with the date and embed the time, so a reverse
    lexicographic sort yields newest-first ordering.
    """
    if not directory.exists():
        return []
    files = [
        (path.stem, path)
        for path in directory.glob("*.md")
        if path.is_file() and _ENTRY_RE.match(path.stem)
    ]
    files.sort(key=lambda f: f[0], reverse=True)
    return files


def list_files() -> list[tuple[str, Path]]:
    """Return (entry_id, path) for available entries, newest first."""
    return _list_entry_files(JOURNAL_DIR)


def list_trashed() -> list[tuple[str, Path]]:
    """Return (entry_id, path) for soft-deleted entries, newest first."""
    return _list_entry_files(_deleted_dir())


def read_entry(entry_id: str) -> str | None:
    """Return the Markdown body for an entry id, or None if it does not exist."""
    if not _ENTRY_RE.match(entry_id):
        return None
    path = JOURNAL_DIR / f"{entry_id}.md"
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def read_trashed_entry(entry_id: str) -> str | None:
    """Return the Markdown body for a soft-deleted entry, or None if absent.

    Mirrors ``read_entry`` but reads from the trash directory so the UI can
    preview an entry's content before deciding whether to restore or purge it.
    """
    if not _ENTRY_RE.match(entry_id):
        return None
    path = _deleted_dir() / f"{entry_id}.md"
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Restore/purge can move or delete the file between the check above and
        # the read; treat that race as a normal not-found rather than a 500.
        return None


def _deleted_dir() -> Path:
    """Return the trash directory for soft-deleted entries."""
    return JOURNAL_DIR / "deleted"


def soft_delete(entry_id: str) -> bool:
    """Move an active entry into the trash directory.

    Returns True if the entry was found and moved, False if it does not exist.
    Because ``list_files`` only globs the top-level directory, a moved entry is
    automatically excluded from listings without any per-query filtering.
    """
    if not _ENTRY_RE.match(entry_id):
        return False
    src = JOURNAL_DIR / f"{entry_id}.md"
    if not src.exists() or not src.is_file():
        return False
    trash = _deleted_dir()
    trash.mkdir(parents=True, exist_ok=True)
    src.replace(trash / f"{entry_id}.md")
    item_src = _item_path(entry_id)
    if item_src.exists():
        item_src.replace(trash / f"{entry_id}.json")
    return True


def restore(entry_id: str) -> bool:
    """Move a soft-deleted entry back into the active directory.

    Returns True if a trashed entry was found and restored, False otherwise.
    Restoring over an existing active entry is refused (returns False).
    """
    if not _ENTRY_RE.match(entry_id):
        return False
    src = _deleted_dir() / f"{entry_id}.md"
    if not src.exists() or not src.is_file():
        return False
    dst = JOURNAL_DIR / f"{entry_id}.md"
    if dst.exists():
        return False
    src.replace(dst)
    item_src = _deleted_dir() / f"{entry_id}.json"
    if item_src.exists():
        item_src.replace(_item_path(entry_id))
    return True


def purge(entry_id: str) -> bool:
    """Permanently delete a soft-deleted entry from the trash directory.

    Returns True if a trashed entry was found and removed, False otherwise.
    """
    if not _ENTRY_RE.match(entry_id):
        return False
    path = _deleted_dir() / f"{entry_id}.md"
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    item = _deleted_dir() / f"{entry_id}.json"
    if item.exists():
        item.unlink()
    return True
