#!/bin/sh
# Install the host's exported Claude login into the container's Claude config dir,
# without replacing a fresher one.
#
#   install-claude-credentials.sh <exported .credentials.json> <installed .credentials.json>
#
# The installed file lives in a persistent volume. If the CLI refreshed its tokens
# inside the container, blindly copying the host export on every start would put a
# stale login back (and with rotating refresh tokens, break every call). So the
# export only replaces the installed file when there is none, or when its access
# token expires later. Re-running docker/sync-claude-auth.sh after a host login
# change therefore takes effect on the next start.
set -eu

src="$1"
dest="$2"

# Expiry of the access token in milliseconds, 0 when the file is missing or unreadable.
expires() {
  node -e '
    try {
      const j = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"))
      console.log(Math.trunc(Number(j.claudeAiOauth.expiresAt)) || 0)
    } catch { console.log(0) }
  ' "$1" 2>/dev/null || echo 0
}

install_copy() {
  umask 077
  cp "$src" "$dest"
  chmod 600 "$dest"
}

if [ ! -s "$src" ]; then
  if [ -s "$dest" ]; then
    echo "brief-lens: no host login at $src; keeping the login already in the container." >&2
  else
    echo "brief-lens: no Claude credentials at $src." >&2
    echo "  Run docker/sync-claude-auth.sh on the host, then restart the container." >&2
  fi
  exit 0
fi

if [ ! -s "$dest" ]; then
  install_copy
  exit 0
fi

if [ "$(expires "$src")" -gt "$(expires "$dest")" ]; then
  install_copy
  echo "brief-lens: installed the newer host login." >&2
else
  echo "brief-lens: keeping the container's login (the host export is not newer)." >&2
fi
