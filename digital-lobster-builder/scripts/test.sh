#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$PROJECT_ROOT"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  exec "$PROJECT_ROOT/.venv/bin/python" -m pytest "$@"
fi

exec uv run python -m pytest "$@"
