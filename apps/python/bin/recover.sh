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
source "$PROJECT_ROOT/.venv/bin/activate"

PYTHONPATH="$PROJECT_ROOT" python -m src.recovery_handler
