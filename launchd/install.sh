#!/usr/bin/env bash
set -euo pipefail

PLIST_NAME="com.aiagent.run.plist"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/log"

# ログディレクトリを作成
mkdir -p "$LOG_DIR"

# 既存エージェントを停止してから上書き
if launchctl list | grep -q "com.aiagent.run"; then
    echo "既存のエージェントをアンロードします..."
    launchctl unload "$PLIST_DEST"
fi

cp "$PLIST_SRC" "$PLIST_DEST"
launchctl load "$PLIST_DEST"

echo "インストール完了: $PLIST_DEST"
echo "次回実行: 毎朝 8:00"
echo "ログ: $LOG_DIR/launchd.stdout.log / launchd.stderr.log"
