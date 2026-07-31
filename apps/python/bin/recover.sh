#!/usr/bin/env bash
# Re-run today's sector sweep when the 05:00 briefing lost it to a DarkWake
# sleep. No-op when today's briefing is already complete, so it is safe to
# schedule several times a day.
set -euo pipefail

# caffeinate keeps the Mac up for the duration once it is genuinely awake. It
# cannot prevent a DarkWake maintenance sleep on battery power, which is why
# recovery_handler checks is_system_awake() before spending anything.
if command -v caffeinate >/dev/null 2>&1 && [ -z "${CAFFEINATED:-}" ]; then
    export CAFFEINATED=1
    exec caffeinate -ims "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .env is sourced by the repo-root wrapper (../../bin/recover.sh) before exec.
# launchd reports only a non-zero exit status, so say why the run died instead
# of letting `source` fail with a bare "No such file or directory".
VENV_ACTIVATE="${VENV_ACTIVATE:-$PROJECT_ROOT/.venv/bin/activate}"
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "recover.sh: virtualenv not found at $VENV_ACTIVATE" >&2
    echo "  create it with: cd $PROJECT_ROOT && uv venv .venv && uv pip sync requirements.txt" >&2
    echo "  or point VENV_ACTIVATE at an existing activate script" >&2
    exit 1
fi
source "$VENV_ACTIVATE"

PYTHONPATH="$PROJECT_ROOT" python -m src.recovery_handler
