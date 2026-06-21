#!/usr/bin/env bash
# Archive a month's briefing markdown files into a zip and upload to Google Drive
# via rclone (zero-cost). Runnable manually, from launchd, or via POST /api/archive.
#
# Usage: archive.sh [--month YYYY-MM] [--prune]
#   --month  Target month (default: previous month).
#   --prune  Delete local md files after a successful upload (default: keep).
#
# Env overrides (mainly for tests):
#   ARCHIVE_BRIEFING_DIR  Source dir of *_YYYY-MM-*.md (default: apps/python/output/briefing)
#   ARCHIVE_OUTPUT_DIR    Where the zip is written     (default: apps/python/output/archive)
#   RCLONE_REMOTE         rclone remote name           (default: gdrive)
#   RCLONE_PATH           Remote path under the remote (default: ai-agent/briefing)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

BRIEFING_DIR="${ARCHIVE_BRIEFING_DIR:-$PROJECT_ROOT/apps/python/output/briefing}"
OUTPUT_DIR="${ARCHIVE_OUTPUT_DIR:-$PROJECT_ROOT/apps/python/output/archive}"
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
RCLONE_PATH="${RCLONE_PATH:-ai-agent/briefing}"

MONTH=""
PRUNE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --month) MONTH="$2"; shift 2 ;;
        --prune) PRUNE=1; shift ;;
        *) echo "error: unknown argument: $1" >&2; exit 2 ;;
    esac
done

# Default to the previous month (BSD/macOS and GNU/Linux variants).
if [ -z "$MONTH" ]; then
    if date -v-1m +%Y-%m >/dev/null 2>&1; then
        MONTH="$(date -v-1m +%Y-%m)"
    else
        MONTH="$(date -d 'last month' +%Y-%m)"
    fi
fi

if ! [[ "$MONTH" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    echo "error: --month must be YYYY-MM, got: $MONTH" >&2
    exit 2
fi

# Collect this month's md files; skip (success) when there are none.
shopt -s nullglob
files=( "$BRIEFING_DIR"/*_"$MONTH"-*.md )
shopt -u nullglob
if [ ${#files[@]} -eq 0 ]; then
    echo "skip: no briefing files for $MONTH in $BRIEFING_DIR"
    exit 0
fi

if ! command -v rclone >/dev/null 2>&1; then
    echo "error: rclone not found. Install it and configure a remote:" >&2
    echo "       brew install rclone && rclone config   # create remote '$RCLONE_REMOTE'" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
ZIP_PATH="$OUTPUT_DIR/briefing_$MONTH.zip"
rm -f "$ZIP_PATH"
zip -j "$ZIP_PATH" "${files[@]}"
echo "created: $ZIP_PATH (${#files[@]} files)"

if ! rclone copy "$ZIP_PATH" "$RCLONE_REMOTE:$RCLONE_PATH/"; then
    echo "error: rclone upload failed. Check that remote '$RCLONE_REMOTE' is configured:" >&2
    echo "       rclone config   # then re-run" >&2
    exit 1
fi
echo "uploaded: $RCLONE_REMOTE:$RCLONE_PATH/briefing_$MONTH.zip"

if [ "$PRUNE" -eq 1 ]; then
    rm -f "${files[@]}"
    echo "pruned: ${#files[@]} local md files for $MONTH"
fi
