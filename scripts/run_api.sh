#!/usr/bin/env bash
# Run AiCheck API on Ubuntu server. Uses PORT from .env (default 41791).
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a
PORT="${PORT:-41791}"
exec python -m uvicorn api:app --host 0.0.0.0 --port "$PORT"
