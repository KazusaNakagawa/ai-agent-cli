#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

VENV_ACTIVATE="$PROJECT_ROOT/.venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "error: venv not found at $VENV_ACTIVATE" >&2
    echo "create it first: cd $PROJECT_ROOT && uv venv .venv && uv pip sync requirements.txt" >&2
    exit 1
fi
source "$VENV_ACTIVATE"
PYTHONPATH="$PROJECT_ROOT" exec python -m src.money "$@"
