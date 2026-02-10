#!/usr/bin/env python3
"""Start both AiCheck API and Streamlit dashboard. Reads ports from .env. For autostart."""

import os
import signal
import subprocess
import sys
from pathlib import Path

# Project root = directory of this script
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# Load .env before reading ports
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

API_PORT = int(os.getenv("AICHECK_API_PORT", os.getenv("PORT", "41791")))
DASHBOARD_PORT = int(os.getenv("AICHECK_DASHBOARD_PORT", "41792"))

processes: list[subprocess.Popen] = []


def kill_children(*_args):
    for p in processes:
        if p.poll() is None:
            p.terminate()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, kill_children)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, kill_children)

    api_cmd = [
        sys.executable, "-m", "uvicorn", "api:app",
        "--host", "0.0.0.0", "--port", str(API_PORT),
    ]
    dash_cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(DASHBOARD_PORT),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
    ]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    print(f"Starting API on port {API_PORT}...")
    p_api = subprocess.Popen(api_cmd, cwd=ROOT, creationflags=creationflags)
    processes.append(p_api)

    print(f"Starting dashboard on port {DASHBOARD_PORT}...")
    p_dash = subprocess.Popen(dash_cmd, cwd=ROOT, creationflags=creationflags)
    processes.append(p_dash)

    print(f"API:        http://localhost:{API_PORT}/docs")
    print(f"Dashboard:  http://localhost:{DASHBOARD_PORT}")
    print("Press Ctrl+C to stop both.")

    # Wait for both; if one exits, we still keep the other running until Ctrl+C
    try:
        p_api.wait()
        p_dash.wait()
    except KeyboardInterrupt:
        pass
    finally:
        kill_children()


if __name__ == "__main__":
    main()
