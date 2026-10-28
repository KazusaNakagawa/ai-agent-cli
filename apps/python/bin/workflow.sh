#!/usr/bin/env bash
set -euo pipefail

# Re-exec under caffeinate so macOS doesn't sleep mid-run: a workflow can make
# long claude CLI calls, and a sleep drops the connection (observed 2026-07-20:
# "Connection closed mid-response", not retried since the message isn't
# classified transient). No-op when caffeinate is unavailable (e.g. CI).
if command -v caffeinate >/dev/null 2>&1 && [ -z "${CAFFEINATED:-}" ]; then
    export CAFFEINATED=1
    exec caffeinate -ims "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

VENV_ACTIVATE="$PROJECT_ROOT/.venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "error: venv not found at $VENV_ACTIVATE" >&2
    echo "create it first: cd $PROJECT_ROOT && uv venv .venv && uv pip sync requirements.txt" >&2
    exit 1
fi
# .env is sourced by the repo-root wrapper (../../bin/workflow.sh) before exec.
source "$VENV_ACTIVATE"

PYTHONPATH="$PROJECT_ROOT" exec python -m src.workflow "$@"
