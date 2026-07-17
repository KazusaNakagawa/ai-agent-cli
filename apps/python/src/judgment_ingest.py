"""Record ingested Notion comments as judgment-learning-loop events (#396).

Comments are free-form human feedback left on an already-published briefing
page, not a formal accept/reject of a not-yet-delivered draft, so every
ingested comment is recorded as a ``judge note`` event under the existing
``brief-gen`` domain — see docs/reports/system-audit-2026-07-17.md §7-4 and
``~/work/dotfiles-claude/docs/learning-loop-design.md``.

The judge CLI and its data store live outside this repo (personal,
single-machine tooling — same ``~/work/<repo>`` layout convention already
used by ``local_llm.config.DEFAULT_REPO_ROOT``), so this module shells out
to it rather than duplicating its schema/ID-numbering logic.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)

JUDGE_BIN = Path.home() / "work" / "dotfiles-claude" / "bin" / "judge"
JUDGE_DOMAIN = "brief-gen"
JUDGE_TIMEOUT_SEC = 10


def judge_available() -> bool:
    return JUDGE_BIN.exists()


def record_comment_as_judgment(comment: dict) -> bool:
    """Run ``judge note`` for one ingested Notion comment. Returns True on success."""
    reason = comment["text"].strip()
    if not reason:
        return False

    context = f"Notion comment on 「{comment['page_title']}」 ({comment['page_date']})"
    cmd = [
        str(JUDGE_BIN), "note",
        "--domain", JUDGE_DOMAIN,
        "--reason", reason,
        "--context", context,
        "--tags", "notion-comment",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=JUDGE_TIMEOUT_SEC)
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("judge note failed for comment %s: %s", comment.get("comment_id"), exc)
        return False
    return True
