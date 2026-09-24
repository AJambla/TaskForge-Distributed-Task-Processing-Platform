#!/usr/bin/env bash
# Run Alembic migrations against the Docker Postgres (bare-metal, using the 3.12 venv).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$BACKEND_DIR"
"$VENV_PY" -m alembic upgrade head
