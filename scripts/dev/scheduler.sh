#!/usr/bin/env bash
# Start the scheduler bare-metal as its OWN process (do not merge into the API:
# APScheduler jobs would double-fire on every uvicorn --reload).
#   scripts/dev/scheduler.sh           -> restart on .py changes
#   scripts/dev/scheduler.sh --debug   -> debugpy on :5680 (no auto-restart)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$BACKEND_DIR"

if [[ "${1:-}" == "--debug" ]]; then
  exec "$VENV_PY" -m debugpy --listen 5680 --wait-for-client -m app.scheduler.main
else
  exec "$VENV_PY" -m watchdog.watchmedo auto-restart \
    --directory=./app --patterns='*.py' --recursive \
    -- "$VENV_PY" -m app.scheduler.main
fi
