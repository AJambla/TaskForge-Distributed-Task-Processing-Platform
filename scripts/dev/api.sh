#!/usr/bin/env bash
# Start the API bare-metal with hot-reload (uvicorn --reload).
#   scripts/dev/api.sh            -> reload, no debugger
#   scripts/dev/api.sh --debug    -> debugpy listening on :5678, then attach from VS Code
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$BACKEND_DIR"

if [[ "${1:-}" == "--debug" ]]; then
  echo ">> API under debugpy (attach on 127.0.0.1:5678). Reload disabled so breakpoints stay stable."
  exec "$VENV_PY" -m debugpy --listen 5678 --wait-for-client \
    -m uvicorn app.main:app --host 127.0.0.1 --port 8000
else
  echo ">> API with --reload on http://localhost:8000 (docs at /docs)"
  exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
fi
