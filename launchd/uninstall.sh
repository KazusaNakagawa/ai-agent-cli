#!/usr/bin/env bash
set -euo pipefail

PLIST_NAME="com.aiagent.run.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

if launchctl list | grep -q "com.aiagent.run"; then
    launchctl unload "$PLIST_DEST"
    echo "エージェントを停止しました"
else
    echo "エージェントは実行されていません"
fi

if [ -f "$PLIST_DEST" ]; then
    rm "$PLIST_DEST"
    echo "削除しました: $PLIST_DEST"
fi
