"""Read and write ``~/.ai-agent/state.json``.

Per-host non-sensitive runtime state. Credentials live in the Keychain
(``src.credentials``) and user settings (portfolio, etc.) in
``apps/python/config/briefing.json``; this file is only for runtime toggles like
"has onboarded" and "is auth_mode cli or api".
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

STATE_FILE = Path.home() / ".ai-agent" / "state.json"
ALLOWED_AUTH_MODES: tuple[str, ...] = ("cli", "api")


@dataclass
class State:
    onboarded: bool = False
    auth_mode: Literal["cli", "api"] = "cli"
    migrated_from_env: bool = False
    version: int = 1


def read_state() -> State:
    if not STATE_FILE.exists():
        return State()
    raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    auth_mode = raw.get("auth_mode", "cli")
    if auth_mode not in ALLOWED_AUTH_MODES:
        raise ValueError(
            f"Invalid auth_mode in {STATE_FILE}: {auth_mode!r}. "
            f"Expected one of {ALLOWED_AUTH_MODES}."
        )
    return State(
        onboarded=raw.get("onboarded", False),
        auth_mode=auth_mode,
        migrated_from_env=raw.get("migrated_from_env", False),
        version=raw.get("version", 1),
    )


def write_state(state: State) -> None:
    if state.auth_mode not in ALLOWED_AUTH_MODES:
        raise ValueError(f"Invalid auth_mode: {state.auth_mode}")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: tempfile in the same directory, then os.replace.
    # Avoids leaving a truncated state.json behind if the process dies mid-write.
    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_FILE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
