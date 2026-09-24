#!/usr/bin/env bash
# Start the worker bare-metal. Not an ASGI app, so use watchdog's auto-restart for hot-reload.
#   scripts/dev/worker.sh           -> restart on .py changes
#   scripts/dev/worker.sh --debug   -> debugpy on :5679 (no auto-restart) for breakpoints
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$BACKEND_DIR"

if [[ "${1:-}" == "--debug" ]]; then
  exec "$VENV_PY" -m debugpy --listen 5679 --wait-for-client -m app.worker.main
else
  exec "$VENV_PY" -m watchdog.watchmedo auto-restart \
    --directory=./app --patterns='*.py' --recursive \
    -- "$VENV_PY" -m app.worker.main
fi
