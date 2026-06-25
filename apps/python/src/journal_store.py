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
from datetime import datetime
from pathlib import Path

JOURNAL_DIR = Path(__file__).parents[1] / "output" / "journal"

# Entry id: a date, optionally followed by "_<suffix>" (time and/or collision
# counter). Legacy day files (bare "YYYY-MM-DD") match with no suffix.
_ENTRY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_[0-9A-Za-z-]+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today() -> str:
    """Return today's date as YYYY-MM-DD (local time)."""
    return datetime.now().strftime("%Y-%m-%d")


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
    if not _DATE_RE.match(date):
        raise ValueError(f"Invalid journal date: {date!r}")
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
            entry_id = f"{base}-{n}"
            n += 1


def list_files() -> list[tuple[str, Path]]:
    """Return (entry_id, path) for available entries, newest first.

    Entry ids start with the date and embed the time, so a reverse
    lexicographic sort yields newest-first ordering.
    """
    if not JOURNAL_DIR.exists():
        return []
    files = [
        (path.stem, path)
        for path in JOURNAL_DIR.glob("*.md")
        if path.is_file() and _ENTRY_RE.match(path.stem)
    ]
    files.sort(key=lambda f: f[0], reverse=True)
    return files


def read_entry(entry_id: str) -> str | None:
    """Return the Markdown body for an entry id, or None if it does not exist."""
    if not _ENTRY_RE.match(entry_id):
        return None
    path = JOURNAL_DIR / f"{entry_id}.md"
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
