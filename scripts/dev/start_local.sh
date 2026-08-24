#!/usr/bin/env bash
#
# macOS / Linux launcher for WaterExpert — the Unix equivalent of start_local.ps1.
#
# Usage:
#   ./scripts/dev/start_local.sh [--recreate-venv] [--skip-install] [--port 8000]
#
# It creates the project virtual environment at .ai4s/ (Python 3.12), installs
# requirements.txt, then starts the FastAPI backend, which also serves the
# pre-built frontend at /ui. Build the frontend first:
#
#   cd frontend && npm install && npm run build && cd ..
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_ROOT="$REPO_ROOT/.ai4s"
VENV_PYTHON="$VENV_ROOT/bin/python"
REQUIREMENTS="$REPO_ROOT/requirements.txt"

HOST="127.0.0.1"
PORT=8000
RECREATE_VENV=0
SKIP_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --recreate-venv) RECREATE_VENV=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    --host) HOST="${2:?--host requires a value}"; shift ;;
    --port) PORT="${2:?--port requires a value}"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ "$RECREATE_VENV" == "1" && -d "$VENV_ROOT" ]]; then
  echo "Removing existing virtual environment at $VENV_ROOT ..."
  rm -rf "$VENV_ROOT"
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Creating virtual environment at $VENV_ROOT ..."
  if command -v uv >/dev/null 2>&1; then
    uv venv "$VENV_ROOT" --python 3.12
  elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv "$VENV_ROOT"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m venv "$VENV_ROOT"
  else
    echo "No Python 3 interpreter found. Install Python 3.12 (or 'uv') first." >&2
    exit 1
  fi
fi

if [[ "$SKIP_INSTALL" != "1" ]]; then
  echo "Installing dependencies with $VENV_PYTHON ..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$VENV_PYTHON" -r "$REQUIREMENTS"
  else
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"
  fi
fi

echo "Starting WaterExpert on http://$HOST:$PORT ..."
cd "$REPO_ROOT"
exec "$VENV_PYTHON" -m uvicorn backend.app.main:app --reload --host "$HOST" --port "$PORT"
