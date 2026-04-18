#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# launchd は /opt/homebrew/bin を含まない最小 PATH で起動するため明示的に追加
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# .env から環境変数を読み込む（launchd はシェル環境を引き継がないため必須）
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

source "$PROJECT_ROOT/.venv/bin/activate"

python "$SCRIPT_DIR/briefing.py"

# レート制限（50k tokens/min）を避けるため briefing 完了後に待機
sleep 60

python "$SCRIPT_DIR/xss_intel.py"
