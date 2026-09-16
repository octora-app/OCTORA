#!/usr/bin/env bash
# OCTORA v1.0 - macOS/Linux launcher
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[OCTORA] python3 not found. Install Python 3.10+ first."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[OCTORA] First run: creating virtual environment..."
    python3 -m venv .venv
    # shellcheck disable=SC1091
    . .venv/bin/activate
    echo "[OCTORA] Installing dependencies (one-time, needs internet)..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    # shellcheck disable=SC1091
    . .venv/bin/activate
fi

echo "[OCTORA] Launching..."
exec python main.py
