#!/usr/bin/env bash
# Create a Python 3.12 venv with uv (uv fetches its own managed 3.12, so you don't
# need 3.12 installed system-wide) and install backend + dev deps.
# Why 3.12: asyncpg/Pillow pin wheels for 3.12; global 3.14 has no cp314 wheels.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo ">> Installing uv (Astral) ..."
  if command -v py >/dev/null 2>&1; then
    py -3.14 -m pip install --user uv
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
fi

# pip --user puts uv.exe in a versioned Scripts dir with backslash Windows paths that
# Git-Bash -f checks mishandle; resolve it via Python and convert with cygpath.
add_uv_to_path() {
  command -v uv >/dev/null 2>&1 && return 0
  local win posix
  win="$(py -3.14 -c 'import uv,os;print(os.path.join(os.path.dirname(uv.__file__),"uv.exe"))' 2>/dev/null || true)"
  [[ -z "$win" ]] && return 1
  posix="$win"
  command -v cygpath >/dev/null 2>&1 && posix="$(cygpath -u "$win")"
  [[ -f "$posix" ]] || return 1
  export PATH="$(dirname "$posix"):$PATH"
}
add_uv_to_path || true
command -v uv >/dev/null 2>&1 || { echo "!! uv not on PATH; add %APPDATA%\\Python\\Python314\\Scripts to PATH"; exit 1; }
echo ">> Using uv: $(command -v uv)"

echo ">> Provisioning managed Python 3.12 ..."
uv python install 3.12

echo ">> Creating .venv (3.12) ..."
uv venv .venv --python 3.12

echo ">> Installing backend requirements + dev requirements ..."
uv pip install --python "$ROOT_DIR/.venv" \
  -r "$BACKEND_DIR/requirements.txt" \
  -r "$BACKEND_DIR/requirements-dev.txt"

echo ">> Done. venv at $ROOT_DIR/.venv"
