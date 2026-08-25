#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# No .env sourcing here (unlike run.sh / chat.sh): importing and reporting read
# only local statement files and config/money_rules.json, and make no LLM or
# network calls, so they need no credentials.
exec "$PROJECT_ROOT/apps/python/bin/money.sh" "$@"
