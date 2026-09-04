"""Record of the last weekly recap that actually reached Notion.

The local ``weekly-summary_<date>.md`` cannot serve as the idempotency marker:
``step_persist`` writes it *before* ``step_deliver_notion``, deliberately, so
the operator keeps a copy when Notion is down. Using it as the marker would
mean a failed delivery still looks like a completed recap, and the week's
recap would be silently lost until someone passed ``--force``. This file is
written only once Notion has accepted the page.

Mirrors ``src.notion_comment_state``: same location, same atomic-write pattern.
"""
import json
import os
import tempfile
from datetime import date
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)

STATE_FILE = Path.home() / ".ai-agent" / "weekly_recap.json"


def week_key(day: date) -> str:
    """ISO week label, e.g. ``2026-W36``.

    The ISO year is not always the calendar year around New Year, which is
    exactly when a naive ``year-week`` string would collide — so the pair comes
    from ``isocalendar()`` rather than from ``day.year``.
    """
    iso_year, iso_week, _ = day.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def read_posted_week() -> str | None:
    """The ISO week of the last delivered recap, or ``None`` if never recorded.

    ``None`` also covers an unreadable or malformed file: the caller's fallback
    is to run the recap, and a duplicate page is a far smaller problem than a
    week with no recap at all.
    """
    if not STATE_FILE.exists():
        return None
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("failed to read %s (%s) — treating the week as not yet recapped", STATE_FILE, exc)
        return None
    if not isinstance(raw, dict):
        logger.warning("unexpected shape in %s (expected dict) — treating the week as not yet recapped", STATE_FILE)
        return None
    week = raw.get("week")
    return week if isinstance(week, str) else None


def record_posted(week: str, page_url: str) -> None:
    """Record ``week`` as delivered. Never raises.

    Called after the Notion page exists, so raising here would fail a run that
    actually succeeded. A failure to record costs at most one duplicate page on
    a later invocation, which is why it is logged rather than propagated.
    """
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: tempfile in the same directory, then os.replace.
        fd, tmp_path = tempfile.mkstemp(dir=str(STATE_FILE.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"week": week, "page_url": page_url}, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, STATE_FILE)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise
    except OSError:
        logger.exception("failed to record the delivered recap week (%s) in %s", week, STATE_FILE)
