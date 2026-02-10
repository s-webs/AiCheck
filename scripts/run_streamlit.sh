#!/usr/bin/env bash
# Run AiCheck Streamlit dashboard. Uses AICHECK_DASHBOARD_PORT from .env (default 41792).
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a
PORT="${AICHECK_DASHBOARD_PORT:-41792}"
exec python -m streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0
