"""Journal <-> Notion sync (best-effort, no retry).

One journal entry maps to one Notion page: new entries create a page; edits
append to the page created for that entry (falling back to creating one if
the entry predates sync, per docs/superpowers/specs/2026-07-03-journal-notion-sync-design.md).
"""
import re

from notion_client import Client

from src import journal_store
from src.logger import get_logger
from src.notifier.markdown import markdown_to_notion_blocks
from src.notifier.notion import _append_blocks, _create_page

logger = get_logger(__name__)

_LEADING_MARKS_RE = re.compile(r"^[\s#\-*]+")
_ROLE_LABEL_RE = re.compile(r"^\*\*(You|AI):\*\*$")
_TITLE_MAX_LEN = 50


def title_from_content(content: str, fallback: str) -> str:
    """Derive a Notion page title from an entry's first non-blank content line.

    Skips role-label lines (e.g. ``**You:**``, ``**AI:**``) produced by
    apps/web/lib/journalQa.ts, strips leading heading/list markers from the
    first remaining line, falls back to ``fallback`` (the entry's date) if
    nothing remains, and truncates to 50 chars.
    """
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or _ROLE_LABEL_RE.match(stripped):
            continue
        title = _LEADING_MARKS_RE.sub("", stripped).strip()
        if title:
            return title[:_TITLE_MAX_LEN]
    return fallback[:_TITLE_MAX_LEN]


def sync_new_entry(entry_id: str, content: str, api_key: str, database_id: str) -> None:
    """Create a Notion page for a newly created journal entry."""
    if not api_key or not database_id:
        return
    notion = Client(auth=api_key)
    title = title_from_content(content, journal_store.date_of(entry_id))
    response = _create_page(notion, database_id, title, markdown_to_notion_blocks(content))
    if response:
        journal_store.save_notion_meta(entry_id, response["id"], response.get("url", ""))


def sync_append(entry_id: str, content: str, api_key: str, database_id: str) -> None:
    """Append to the journal entry's Notion page, creating one if it has none yet."""
    if not api_key or not database_id:
        return
    notion = Client(auth=api_key)
    blocks = markdown_to_notion_blocks(content)
    page_id = journal_store.get_notion_meta(entry_id)
    if page_id:
        _append_blocks(notion, page_id, blocks)
        return

    title = title_from_content(content, journal_store.date_of(entry_id))
    response = _create_page(notion, database_id, title, blocks)
    if response:
        journal_store.save_notion_meta(entry_id, response["id"], response.get("url", ""))
