#!/usr/bin/env bash
# Run AiCheck Streamlit UI on Ubuntu server. Uses PORT from .env (default 41791).
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a
PORT="${PORT:-41791}"
exec python -m streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0
