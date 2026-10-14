#!/usr/bin/env bash
# Smart Energy Guardian — run everything locally with one command (macOS / Linux).
# Needs Python 3.11+ and Node.js 20+.  Usage: ./run-local.sh [--rebuild]
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "Python 3.11+ is required: https://www.python.org/downloads/"; exit 1; }
command -v npm >/dev/null || { echo "Node.js 20+ is required: https://nodejs.org/"; exit 1; }

if [ ! -x backend/.venv/bin/python ]; then
  echo "==> Creating Python virtual environment"
  "$PY" -m venv backend/.venv
fi
if [ ! -f backend/.venv/.installed ] || [ backend/requirements.txt -nt backend/.venv/.installed ]; then
  echo "==> Installing backend dependencies"
  backend/.venv/bin/python -m pip install -q --upgrade pip
  backend/.venv/bin/python -m pip install -q -r backend/requirements.txt
  touch backend/.venv/.installed
fi
if [ ! -f frontend/dist/index.html ] || [ "${1:-}" = "--rebuild" ]; then
  echo "==> Building the dashboard"
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi

PORT="${PORT:-8000}"
echo
echo "==> Smart Energy Guardian: http://localhost:${PORT}   (login: admin / guardian-demo)"
echo "    API docs: http://localhost:${PORT}/docs   — press Ctrl+C to stop"
echo
cd backend
exec .venv/bin/python -m uvicorn app.asgi:app --host 0.0.0.0 --port "$PORT"
