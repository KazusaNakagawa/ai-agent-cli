"""Owner-only permissions for personal data (files 0600, directories 0700).

Personal config, raw statements and generated reports must not be readable by
other local users. Writers go through ``write_private_text`` /
``ensure_private_dir``; ``warn_loose_permissions`` reports anything that is
group/world accessible without changing it, so a surprising mode is the
owner's decision.
"""
import logging
import os
import stat
from collections.abc import Iterable
from pathlib import Path

from src import paths

logger = logging.getLogger(__name__)

PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700
_LOOSE_BITS = 0o077

PERSONAL_CONFIG_FILES = (
    "briefing.json",
    "holdings.json",
    "money_rules.json",
    "self_agent_profile.md",
)


def ensure_private_dir(path: Path) -> None:
    """Create ``path`` (and parents) and make the leaf directory 0700."""
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(PRIVATE_DIR_MODE)


def write_private_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` with mode 0600, tightening an existing file."""
    ensure_private_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
    finally:
        # os.open's mode is ignored for a file that already exists.
        path.chmod(PRIVATE_FILE_MODE)


def personal_paths() -> list[Path]:
    """Files and directories that hold personal data."""
    files = [paths.CONFIG_DIR / name for name in PERSONAL_CONFIG_FILES]
    return [*files, paths.INPUT_DIR, paths.OUTPUT_DIR]


def _loose_entries(candidates: Iterable[Path]) -> list[tuple[Path, int, bool]]:
    """Return ``(path, mode, is_dir)`` for existing paths open to group/others.

    Each path is stat'ed once, so a path removed mid-check cannot raise later.
    """
    loose = []
    for path in candidates:
        try:
            st = path.stat()
        except FileNotFoundError:
            continue
        mode = stat.S_IMODE(st.st_mode)
        if mode & _LOOSE_BITS:
            loose.append((path, mode, stat.S_ISDIR(st.st_mode)))
    return loose


def find_loose_paths(candidates: Iterable[Path]) -> list[Path]:
    """Return existing paths readable/writable by group or others."""
    return [path for path, _, _ in _loose_entries(candidates)]


def warn_loose_permissions(candidates: Iterable[Path] | None = None) -> list[Path]:
    """Log one warning per loose path (path and mode only) and return them."""
    entries = _loose_entries(personal_paths() if candidates is None else candidates)
    for path, mode, is_dir in entries:
        expected = PRIVATE_DIR_MODE if is_dir else PRIVATE_FILE_MODE
        logger.warning(
            "personal data is accessible to other users: %s has mode %03o (expected %03o); "
            "fix with: chmod %03o %s",
            path, mode, expected, expected, path,
        )
    return [path for path, _, _ in entries]
