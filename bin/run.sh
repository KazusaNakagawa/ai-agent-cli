#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Source .env so cron/non-interactive shells pick up API credentials.
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

source "$PROJECT_ROOT/.venv/bin/activate"

python "$SCRIPT_DIR/briefing.py"
# python "$SCRIPT_DIR/xss_intel.py"

# 金曜日のみ週次振り返りを日次実行後に実行 (1=月 … 5=金)
if [ "$(date +%u)" = "5" ]; then
    python "$SCRIPT_DIR/weekly_summary.py"
fi
