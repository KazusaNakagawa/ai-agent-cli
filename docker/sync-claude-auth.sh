#!/usr/bin/env bash
# Copy the host's Claude Code login into a directory the container mounts read-only.
#
#   docker/sync-claude-auth.sh
#
# macOS keeps the login in the Keychain, which a Linux container cannot read, so
# this exports it to a file. On Linux the CLI already keeps it in a file.
# The token is never printed. Re-run after the login changes or expires.
set -euo pipefail

OUT_DIR="${BRIEF_LENS_AUTH_DIR:-$HOME/.brief-lens-docker/claude-auth}"
SERVICE="Claude Code-credentials"

read_credentials() {
  case "$(uname -s)" in
    Darwin)
      # Claude Code stores the item under the OS user name; fall back to a
      # service-only lookup for installs that used another account name.
      security find-generic-password -s "$SERVICE" -a "$USER" -w 2>/dev/null \
        || security find-generic-password -s "$SERVICE" -w 2>/dev/null
      ;;
    *)
      cat "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json" 2>/dev/null
      ;;
  esac
}

if ! creds="$(read_credentials)" || [ -z "$creds" ]; then
  echo "sync-claude-auth: no Claude login found on this machine." >&2
  echo "  Run \`claude\` once and log in, then run this script again." >&2
  exit 1
fi

# Optional sanity check (needs python3): valid JSON, and the access token not
# yet expired. An expired token is still copied — the CLI refreshes it with the
# refresh token — but say so, because a refresh inside the container is the one
# thing this setup has not been verified to survive (see docs/guides/docker.md).
if command -v python3 >/dev/null 2>&1; then
  status="$(printf '%s' "$creds" | python3 -c '
import json, sys, time
try:
    oauth = json.load(sys.stdin)["claudeAiOauth"]
except Exception:
    print("invalid"); raise SystemExit
exp = oauth.get("expiresAt")
print("expired" if isinstance(exp, (int, float)) and exp / 1000 < time.time() else "ok")
')"
  case "$status" in
    invalid)
      echo "sync-claude-auth: the stored login is not the expected JSON; not copying it." >&2
      exit 1 ;;
    expired)
      echo "sync-claude-auth: the access token has expired. Copying anyway; if requests fail," >&2
      echo "  run \`claude\` on this machine (it refreshes the login) and run this script again." >&2 ;;
  esac
fi

umask 077
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
tmp="$(mktemp "$OUT_DIR/.credentials.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
printf '%s\n' "$creds" > "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$OUT_DIR/.credentials.json"
trap - EXIT

echo "sync-claude-auth: wrote $OUT_DIR/.credentials.json (mode 600)."
echo "  Start the app with: docker compose up --build"
