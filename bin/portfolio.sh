#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# No .env sourcing here (unlike run.sh / chat.sh): the snapshot only reads
# config/holdings.json and public yfinance quotes, so it needs no credentials.
exec "$PROJECT_ROOT/apps/python/bin/portfolio.sh" "$@"
