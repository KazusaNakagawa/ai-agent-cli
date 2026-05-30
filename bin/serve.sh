#!/usr/bin/env bash
# Launch the full Phase 1 Web UI: FastAPI (:8000) + Next.js dev (:3000).
# Use apps/python/bin/serve.sh directly if you only want the backend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON_APP="$PROJECT_ROOT/apps/python"
WEB_APP="$PROJECT_ROOT/apps/web"

# --- flags ---
NO_BROWSER=false
for arg in "$@"; do
    case "$arg" in
        --no-browser) NO_BROWSER=true ;;
        -h|--help)
            cat <<EOF
Usage: bin/serve.sh [--no-browser]

Starts the FastAPI backend (\$API_PORT, default 8000) and the Next.js dev
server (\$WEB_PORT, default 3000), mirrors the bearer token to
apps/web/.token, and opens the browser at the web port. Ctrl-C shuts
both down.

Flags:
  --no-browser   Skip the browser auto-open (also skipped when \$CI is set).
EOF
            exit 0
            ;;
        *)
            echo "unknown flag: $arg" >&2
            echo "try: bin/serve.sh --help" >&2
            exit 2
            ;;
    esac
done

# --- pre-flight ---
if [ ! -x "$PYTHON_APP/.venv/bin/uvicorn" ]; then
    echo "error: uvicorn not found at $PYTHON_APP/.venv/bin/uvicorn" >&2
    echo "       run: cd apps/python && uv pip sync requirements.txt" >&2
    exit 1
fi
if [ ! -d "$WEB_APP/node_modules" ]; then
    echo "error: web dependencies missing at $WEB_APP/node_modules" >&2
    echo "       run: cd apps/web && npm install" >&2
    exit 1
fi

# --- env (.env must be loaded before subprocesses inherit it) ---
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

# --- token: create if missing, mirror to apps/web/.token ---
# Generates the same shape (secrets.token_urlsafe(32)) that
# apps/python/web/auth.py would write on the first authed request, so we
# pre-create it now and both servers read the same value with no race.
TOKEN_FILE="$HOME/.ai-agent/session-token"
mkdir -p "$(dirname "$TOKEN_FILE")"
if [ ! -f "$TOKEN_FILE" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
fi
cp "$TOKEN_FILE" "$WEB_APP/.token"
chmod 600 "$WEB_APP/.token"

# --- process management ---
pids=()
cleanup() {
    trap - INT TERM EXIT
    echo
    echo "Shutting down..."
    for pid in "${pids[@]}"; do
        # npm forks `next dev`; SIGTERM the direct child plus its descendants.
        pkill -P "$pid" 2>/dev/null || true
        kill -TERM "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "ai-agent UI starting..."
echo "  API:  http://127.0.0.1:$API_PORT"
echo "  Web:  http://localhost:$WEB_PORT"
echo "  Press Ctrl-C to stop both"
echo

# Start FastAPI (uvicorn). Delegate to the existing backend launcher so
# its --reload-dir flags stay the single source of truth.
PORT="$API_PORT" "$PYTHON_APP/bin/serve.sh" &
pids+=("$!")

# Start Next.js. Use the package script so it picks up the project's dev config.
( cd "$WEB_APP" && PORT="$WEB_PORT" npm run dev ) &
pids+=("$!")

# --- early-death detection ---
# Give both processes a moment to bind their ports. If either exits before
# this window (most commonly: port collision), surface the failure here
# instead of leaving the user with a half-working stack.
sleep 2
if ! kill -0 "${pids[0]}" 2>/dev/null; then
    echo "error: FastAPI exited early — port $API_PORT may be in use" >&2
    exit 1
fi
if ! kill -0 "${pids[1]}" 2>/dev/null; then
    echo "error: Next.js exited early — port $WEB_PORT may be in use" >&2
    exit 1
fi

# --- browser ---
if [ "$NO_BROWSER" = false ] && [ -z "${CI:-}" ] && command -v open >/dev/null 2>&1; then
    # Poll for Next.js readiness instead of a fixed sleep — first cold start
    # can take 5–10s and a fixed delay races with that. Best-effort: if it
    # never comes up the loop times out and we don't open anything.
    (
        for _ in $(seq 1 30); do
            if curl -fsS --max-time 1 "http://localhost:$WEB_PORT/" >/dev/null 2>&1; then
                open "http://localhost:$WEB_PORT" >/dev/null 2>&1 || true
                exit 0
            fi
            sleep 1
        done
    ) &
fi

wait
