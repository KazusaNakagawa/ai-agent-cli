#!/bin/sh
# Container entrypoint: install the host's Claude credentials, then start brief-lens.
set -eu

AUTH_SRC="${CLAUDE_AUTH_DIR:-/run/claude-auth}/.credentials.json"
APP_USER=node

# As root, HOME is /root; the files below must land where `node` will look.
if [ "$(id -u)" = 0 ]; then
  HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
  export HOME
fi
CLAUDE_HOME="$HOME/.claude"

umask 077
mkdir -p "$CLAUDE_HOME"

# Copy rather than mount the file itself: the host script replaces it with a
# rename, which a single-file bind mount would not follow. Done as root because
# the mount belongs to the host user (0700), whatever uid that is. A login the
# container has already refreshed is kept unless the export is newer.
brief-lens-install-credentials "$AUTH_SRC" "$CLAUDE_HOME/.credentials.json"

# Without this the CLI may start its first-run wizard instead of answering.
if [ ! -e "$HOME/.claude.json" ]; then
  printf '{"hasCompletedOnboarding":true}\n' > "$HOME/.claude.json"
fi

# The API stays on 127.0.0.1 inside the container; only the Web UI is exposed,
# and compose publishes that to the host's loopback.
set -- node /opt/brief-lens/bin/brief-lens.mjs --host 0.0.0.0 --no-browser --home "$BRIEF_LENS_HOME" "$@"

if [ "$(id -u)" = 0 ]; then
  # Hand the copied files to the app user, then give up root and every
  # capability before anything else runs.
  # A file that is absent is skipped; a chown that fails is reported, since the app
  # would otherwise start and then fail with "Not logged in" and no hint in the log.
  for path in "$CLAUDE_HOME" "$CLAUDE_HOME/.credentials.json" "$HOME/.claude.json"; do
    [ -e "$path" ] || continue
    chown "$APP_USER:$APP_USER" "$path" || echo "entrypoint: could not hand $path to $APP_USER" >&2
  done
  exec setpriv --reuid="$APP_USER" --regid="$APP_USER" --init-groups \
    --inh-caps=-all --bounding-set=-all --no-new-privs "$@"
fi
exec "$@"
