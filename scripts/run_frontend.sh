#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../frontend"
[ -d node_modules ] || npm install
[ -f .env ] || cp .env.example .env
echo "Starting dashboard on http://localhost:5173 (backend expected at http://localhost:8000)"
npm run dev
