#!/usr/bin/env bash
# Interactive Q&A session using a daily briefing as context.
# Usage: bin/chat.sh [YYYY-MM-DD|--list]
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
SESSIONS_DIR="$BRIEFING_DIR/.sessions"

# --list: show saved sessions and exit
if [ "${1:-}" = "--list" ]; then
    if [ ! -d "$SESSIONS_DIR" ] || [ -z "$(ls -A "$SESSIONS_DIR" 2>/dev/null)" ]; then
        echo "No saved sessions."
        exit 0
    fi
    echo "Saved chat sessions:"
    for f in "$SESSIONS_DIR"/*; do
        [ -f "$f" ] || continue
        date_part="$(basename "$f")"
        session_id="$(cat "$f")"
        echo "  $date_part  $session_id"
    done
    exit 0
fi

TARGET_DATE="${1:-$(date +%Y-%m-%d)}"
BRIEFING_FILE="$BRIEFING_DIR/briefing_${TARGET_DATE}.md"
SESSION_FILE="$SESSIONS_DIR/${TARGET_DATE}"
SESSION_NAME="briefing-chat-${TARGET_DATE}"

if [ ! -f "$BRIEFING_FILE" ]; then
    echo "Error: briefing file not found: $BRIEFING_FILE" >&2
    echo "Usage: $(basename "$0") [YYYY-MM-DD|--list]" >&2
    exit 1
fi

mkdir -p "$SESSIONS_DIR"

if [ -f "$SESSION_FILE" ]; then
    # Resume existing session — briefing context is already in the conversation history
    SESSION_ID="$(cat "$SESSION_FILE")"
    echo "Resuming session: $SESSION_NAME ($SESSION_ID)"
    echo "(type your question, Ctrl+C or /exit to quit)"
    echo ""
    exec claude \
        --session-id "$SESSION_ID" \
        --name "$SESSION_NAME"
else
    # New session: generate UUID, persist it, inject briefing as context
    SESSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
    echo "$SESSION_ID" > "$SESSION_FILE"

    BRIEFING_CONTENT="$(cat "$BRIEFING_FILE")"
    CONTEXT="以下は ${TARGET_DATE} のマーケットブリーフィングです。このブリーフィングをコンテキストとして、ユーザーの質問に日本語で回答してください。

=== マーケットブリーフィング (${TARGET_DATE}) ===
${BRIEFING_CONTENT}
=== END ==="

    echo "New session: $SESSION_NAME ($SESSION_ID)"
    echo "(type your question, Ctrl+C or /exit to quit)"
    echo ""
    exec claude \
        --session-id "$SESSION_ID" \
        --name "$SESSION_NAME" \
        --append-system-prompt "$CONTEXT"
fi
