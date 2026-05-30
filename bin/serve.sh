#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON_APP="$PROJECT_ROOT/apps/python"

UVICORN="$PYTHON_APP/.venv/bin/uvicorn"
if [ ! -x "$UVICORN" ]; then
    echo "error: uvicorn not found at $UVICORN" >&2
    echo "       run: cd apps/python && uv pip sync requirements.txt" >&2
    exit 1
fi

# .env loads the same way root bin/run.sh does — so launch parity is preserved.
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

TOKEN_FILE="$HOME/.ai-agent/session-token"
TOKEN_DISPLAY="(generated on first request)"
if [ -f "$TOKEN_FILE" ]; then
    TOKEN_DISPLAY="$(cat "$TOKEN_FILE")"
fi

echo "Starting ai-agent Web API at http://127.0.0.1:8000"
echo "Bearer token: $TOKEN_DISPLAY"

cd "$PYTHON_APP"
exec "$UVICORN" web.app:app --host 127.0.0.1 --port 8000 --reload
