#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_APP="$(dirname "$SCRIPT_DIR")"

UVICORN="$PYTHON_APP/.venv/bin/uvicorn"
if [ ! -x "$UVICORN" ]; then
    echo "error: uvicorn not found at $UVICORN" >&2
    echo "       run: cd apps/python && uv pip sync requirements.txt" >&2
    exit 1
fi

# .env is sourced by the repo-root wrapper (../../bin/serve.sh) before exec.
# PORT overridable so a second instance can dodge a collision without forking.
PORT="${PORT:-8000}"

TOKEN_FILE="$HOME/.ai-agent/session-token"
if [ -f "$TOKEN_FILE" ]; then
    TOKEN_HINT="cat $TOKEN_FILE"
else
    TOKEN_HINT="will be created at $TOKEN_FILE on the first authed request"
fi

echo "Starting ai-agent Web API at http://127.0.0.1:$PORT"
echo "Bearer token: $TOKEN_HINT"

cd "$PYTHON_APP"
# --reload-dir scoped to app code so saving a test file doesn't bounce the server.
exec "$UVICORN" web.app:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --reload \
    --reload-dir web \
    --reload-dir src
