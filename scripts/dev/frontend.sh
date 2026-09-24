#!/usr/bin/env bash
# Start the frontend bare-metal with Vite HMR on :5173.
# The app calls the API directly at http://localhost:8000/api/v1 (see VITE_API_URL in
# frontend/src/api/client.ts); CORS in backend/.env already allows :5173.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$FRONTEND_DIR"

[[ -d node_modules ]] || npm install
# Optional: pin API base explicitly (defaults to localhost:8000 already).
# export VITE_API_URL="http://localhost:8000/api/v1"
exec npm run dev
