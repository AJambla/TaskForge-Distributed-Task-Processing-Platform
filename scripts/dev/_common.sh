#!/usr/bin/env bash
# Shared helpers for TaskForge bare-metal dev scripts.
set -euo pipefail

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DEV_DIR/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# The local Python created by bootstrap.sh (matches the 3.12 containers).
VENV_PY="$ROOT_DIR/.venv/Scripts/python.exe"   # Windows venv layout
[[ -x "$VENV_PY" ]] || VENV_PY="$ROOT_DIR/.venv/bin/python"  # *nix fallback

require_venv() {
  if [[ ! -x "$VENV_PY" ]]; then
    echo "!! No .venv found. Run scripts/dev/bootstrap.sh first." >&2
    exit 1
  fi
}
