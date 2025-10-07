#!/usr/bin/env bash
set -euo pipefail

if [ -f .vite.pid ]; then
  kill "$(head -n1 .vite.pid)" 2>/dev/null || true
  rm -f .vite.pid
fi
pkill -f "uvicorn server.app:app" 2>/dev/null || true
