#!/usr/bin/env bash
# Run AiCheck API. Uses AICHECK_API_PORT from .env (default 41791).
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a
PORT="${AICHECK_API_PORT:-41791}"
exec python -m uvicorn api:app --host 0.0.0.0 --port "$PORT"
