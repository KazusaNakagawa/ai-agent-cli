#!/usr/bin/env bash
set -euo pipefail

# Re-exec under caffeinate so macOS doesn't sleep mid-run and drop the claude
# CLI's network connection (observed 2026-07-20: "Connection closed
# mid-response" on both claude CLI calls, not retried since the message
# isn't classified transient). No-op when caffeinate is unavailable (e.g. CI).
if command -v caffeinate >/dev/null 2>&1 && [ -z "${CAFFEINATED:-}" ]; then
    export CAFFEINATED=1
    exec caffeinate -ims "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .env is sourced by the repo-root wrapper (../../bin/run.sh) before exec.
source "$PROJECT_ROOT/.venv/bin/activate"

PYTHONPATH="$PROJECT_ROOT" python -m src.handler
# PYTHONPATH="$PROJECT_ROOT" python -m src.xss_handler

# 週次振り返り。「金曜のみ」の判定はワークフローの guard が持つので、ここは
# 毎日呼んでよい (WEEKLY_RECAP_WEEKDAY 以外の日は skipped で即終了する)。
# bin/workflow.sh run weekly でも同じものが走る。
PYTHONPATH="$PROJECT_ROOT" python -m src.workflow run weekly
