#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PORT="${1:-8000}"
[ -d .venv ] || { python3 -m venv .venv; ./.venv/bin/pip install -r requirements.txt; }
echo "Starting solver backend on http://localhost:$PORT ..."
./.venv/bin/python -m uvicorn solver.api.app:app --host 0.0.0.0 --port "$PORT" --reload
