#!/usr/bin/env bash
# Interactive Q&A session using a daily briefing as context.
# Usage: bin/chat.sh [YYYY-MM-DD]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

BRIEFING_DIR="$PROJECT_ROOT/output/briefing"
TARGET_DATE="${1:-$(date +%Y-%m-%d)}"
BRIEFING_FILE="$BRIEFING_DIR/briefing_${TARGET_DATE}.md"

if [ ! -f "$BRIEFING_FILE" ]; then
    echo "Error: briefing file not found: $BRIEFING_FILE" >&2
    echo "Usage: $(basename "$0") [YYYY-MM-DD]" >&2
    exit 1
fi

BRIEFING_CONTENT="$(cat "$BRIEFING_FILE")"

CONTEXT="以下は ${TARGET_DATE} のマーケットブリーフィングです。このブリーフィングをコンテキストとして、ユーザーの質問に日本語で回答してください。

=== マーケットブリーフィング (${TARGET_DATE}) ===
${BRIEFING_CONTENT}
=== END ==="

SESSION_NAME="briefing-chat-${TARGET_DATE}"

echo "Loaded: $BRIEFING_FILE"
echo "Session: $SESSION_NAME"
echo "(type your question, Ctrl+C or /exit to quit)"
echo ""

exec claude \
    --name "$SESSION_NAME" \
    --append-system-prompt "$CONTEXT"
