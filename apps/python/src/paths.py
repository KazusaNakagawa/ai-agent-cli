"""Single source of truth for where the app reads and writes files.

Writable data (config, output, log, input, session state) hangs off one data
home so an ``npx brief-lens`` install can keep user data outside the package:

- ``BRIEF_LENS_HOME`` set → everything lives under that directory.
- unset → the historical clone layout: data under ``apps/python/`` and session
  state under ``~/.ai-agent/``. Clone users and CI see no change.

Read-only assets shipped with the code (``prompts/``, ``bin/``, ``*.example``)
always resolve relative to the source tree.

Values are resolved once at import time, like the module-level constants they
replace; the launcher sets the env var before starting any process.
"""
import os
from collections.abc import Mapping
from pathlib import Path

HOME_ENV = "BRIEF_LENS_HOME"

# apps/python/ — the source tree root, used for read-only assets and as the
# default data home.
APP_ROOT = Path(__file__).resolve().parents[1]


def _env_home(env: Mapping[str, str]) -> Path | None:
    raw = env.get(HOME_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def resolve_data_home(env: Mapping[str, str] = os.environ) -> Path:
    """Return the root for config/output/log/input."""
    return _env_home(env) or APP_ROOT


def resolve_state_dir(env: Mapping[str, str] = os.environ) -> Path:
    """Return the directory for session state (token, state.json, ingest cursors)."""
    return _env_home(env) or Path.home() / ".ai-agent"


DATA_HOME = resolve_data_home()
CONFIG_DIR = DATA_HOME / "config"
OUTPUT_DIR = DATA_HOME / "output"
LOG_DIR = DATA_HOME / "log"
INPUT_DIR = DATA_HOME / "input"

STATE_DIR = resolve_state_dir()
TOKEN_FILE = STATE_DIR / "session-token"

PROMPTS_DIR = APP_ROOT / "prompts"
BIN_DIR = APP_ROOT / "bin"
EXAMPLE_CONFIG_DIR = APP_ROOT / "config"
