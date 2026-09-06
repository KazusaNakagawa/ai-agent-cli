#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .env is sourced here, not in the inner script: a workflow may deliver to
# Discord/Notion or call the claude CLI, so credentials have to be present.
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

exec "$PROJECT_ROOT/apps/python/bin/workflow.sh" "$@"
