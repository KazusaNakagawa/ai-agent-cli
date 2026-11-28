#!/bin/sh
# Container entrypoint: install the host's Claude credentials, then start brief-lens.
set -eu

AUTH_SRC="${CLAUDE_AUTH_DIR:-/run/claude-auth}/.credentials.json"
CLAUDE_HOME="$HOME/.claude"

umask 077
mkdir -p "$CLAUDE_HOME"

if [ -s "$AUTH_SRC" ]; then
  # Copy rather than mount the file itself: the host script replaces it with a
  # rename, which a single-file bind mount would not follow.
  cp "$AUTH_SRC" "$CLAUDE_HOME/.credentials.json"
  chmod 600 "$CLAUDE_HOME/.credentials.json"
else
  echo "brief-lens: no Claude credentials at $AUTH_SRC." >&2
  echo "  Run docker/sync-claude-auth.sh on the host, then restart the container." >&2
fi

# Without this the CLI may start its first-run wizard instead of answering.
if [ ! -e "$HOME/.claude.json" ]; then
  printf '{"hasCompletedOnboarding":true}\n' > "$HOME/.claude.json"
fi

# The API stays on 127.0.0.1 inside the container; only the Web UI is exposed,
# and compose publishes that to the host's loopback.
exec node /opt/brief-lens/bin/brief-lens.mjs --host 0.0.0.0 --no-browser --home "$BRIEF_LENS_HOME" "$@"
