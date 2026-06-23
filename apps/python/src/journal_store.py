"""Journal store — append and read daily Markdown notes.

The journaling agent accumulates free-form daily notes (thoughts, what
happened today) so they can later be used as context for brainstorming.

Storage layout: one Markdown file per day under ``JOURNAL_DIR`` named
``YYYY-MM-DD.md``. Each appended note becomes a timestamped section so a
single day can hold many entries while staying human-readable.

``JOURNAL_DIR`` lives under ``output/`` which is gitignored, so personal
notes are never committed (matches the briefing output convention).
"""
import re
from datetime import datetime
from pathlib import Path

JOURNAL_DIR = Path(__file__).parents[1] / "output" / "journal"

# Journal file names are exactly a date: YYYY-MM-DD.md (no path separators).
_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today() -> str:
    """Return today's date as YYYY-MM-DD (local time)."""
    return datetime.now().strftime("%Y-%m-%d")


def _path_for(date: str) -> Path:
    """Return the file path for a date, validating the date format first."""
    if not _DATE_RE.match(date):
        raise ValueError(f"Invalid journal date: {date!r}")
    return JOURNAL_DIR / f"{date}.md"


def append_entry(content: str, date: str | None = None) -> str:
    """Append a timestamped note to the day's file, creating it if absent.

    Returns the date (YYYY-MM-DD) the note was written to. A new file is
    seeded with a ``# Journal {date}`` heading before the first section.
    """
    text = content.strip()
    if not text:
        raise ValueError("Journal entry content must not be empty")

    date = date or _today()
    path = _path_for(date)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%H:%M:%S")
    section = f"## {timestamp}\n\n{text}\n"

    if path.exists():
        existing = path.read_text(encoding="utf-8").rstrip("\n")
        path.write_text(f"{existing}\n\n{section}", encoding="utf-8")
    else:
        path.write_text(f"# Journal {date}\n\n{section}", encoding="utf-8")
    return date


def list_dates() -> list[str]:
    """Return available journal dates, newest first."""
    if not JOURNAL_DIR.exists():
        return []
    dates = [
        m.group(1)
        for path in JOURNAL_DIR.glob("*.md")
        if path.is_file() and (m := _FILE_RE.match(path.name))
    ]
    dates.sort(reverse=True)
    return dates


def read_entry(date: str) -> str | None:
    """Return the Markdown body for a date, or None if it does not exist."""
    if not _DATE_RE.match(date):
        return None
    path = JOURNAL_DIR / f"{date}.md"
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
