"""Read and write ``~/.ai-agent/ingested_notion_comments.json``.

Tracks which Notion comment IDs have already been ingested into the
judgment learning loop (#396), so a re-run of the weekly batch doesn't
duplicate ``judgments.jsonl`` entries. Mirrors ``src.state``'s atomic-write
pattern.
"""
import json
import os
import tempfile
from pathlib import Path

STATE_FILE = Path.home() / ".ai-agent" / "ingested_notion_comments.json"


def read_seen_ids() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    ids = raw.get("ids")
    return set(ids) if isinstance(ids, list) else set()


def write_seen_ids(ids: set[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: tempfile in the same directory, then os.replace.
    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_FILE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"ids": sorted(ids)}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
