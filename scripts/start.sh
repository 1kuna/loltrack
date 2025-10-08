#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv || true
. ./.venv/bin/activate
pip install -U pip
# Install core + backend
pip install -e .
pip install -e backend

if [ -d frontend ]; then
  pushd frontend >/dev/null
  if [ -f package.json ]; then
    if [ ! -d node_modules ]; then
      if [ -f package-lock.json ]; then
        npm ci
      else
        npm install
      fi
    fi
  fi
  popd >/dev/null
else
  echo "No frontend found (frontend/). Backend will run without UI."
fi

export PORT=${PORT:-8787}
if [ "${PROD:-}" = "1" ]; then
  if [ -d frontend ]; then (cd frontend && npm run build); fi
  uvicorn server.app:app --host 127.0.0.1 --port "$PORT" &
  sleep 1; (open "http://127.0.0.1:${PORT}/" 2>/dev/null || true)
  wait
else
  if [ -d frontend ]; then (cd frontend && { npm run dev & echo $! > ../.vite.pid; }); fi
  uvicorn server.app:app --reload --host 127.0.0.1 --port "$PORT"
fi
