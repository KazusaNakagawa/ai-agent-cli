#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .env is sourced by the repo-root wrapper (../../bin/chat.sh) before exec.
source "$PROJECT_ROOT/.venv/bin/activate"
# PYTHONPATH makes `from src.chat_session import ...` resolve when chat.py
# is run as a script. Avoids sys.path mutation inside the script.
PYTHONPATH="$PROJECT_ROOT" exec python "$SCRIPT_DIR/chat.py" "$@"
