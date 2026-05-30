#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .env is sourced by the repo-root wrapper (../../bin/chat.sh) before exec.
source "$PROJECT_ROOT/.venv/bin/activate"
exec python "$SCRIPT_DIR/chat.py" "$@"
