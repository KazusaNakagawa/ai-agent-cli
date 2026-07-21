"""Journal -> Obsidian vault one-way sync (best-effort).

An Obsidian vault is a plain folder of Markdown files, so syncing an entry
means writing its full current content to
``<vault>/<journal_subdir>/<entry_id>.md``. The local journal entry is the
source of truth: every sync overwrites the vault copy, so no incremental /
append bookkeeping (like the Notion page-id mapping) is needed.
"""
from pathlib import Path

from src import journal_store
from src.logger import get_logger

logger = get_logger(__name__)


def sync_entry(entry_id: str, vault_path: Path, journal_subdir: str) -> None:
    """Write the entry's full content into the vault, overwriting any copy.

    Never raises for expected failure modes (missing vault, missing entry):
    this runs as a best-effort background task and must not disturb the
    caller. Unexpected I/O errors propagate to the caller's guard.
    """
    content = journal_store.read_entry(entry_id)
    if content is None:
        logger.warning("obsidian sync skipped: journal entry not found: %s", entry_id)
        return
    if not vault_path.is_dir():
        logger.warning("obsidian sync skipped: vault path does not exist: %s", vault_path)
        return
    dest_dir = vault_path / journal_subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / f"{entry_id}.md").write_text(content, encoding="utf-8")
