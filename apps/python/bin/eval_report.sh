#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$PROJECT_ROOT/.venv/bin/activate"

echo "=== eval: extract ==="
PYTHONPATH="$PROJECT_ROOT" python -m src.evaluator extract

echo "=== eval: score ==="
PYTHONPATH="$PROJECT_ROOT" python -m src.evaluator score

echo "=== eval: report ==="
PYTHONPATH="$PROJECT_ROOT" python -m src.evaluator report

echo "=== done ==="
