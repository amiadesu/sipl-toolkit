#!/bin/bash

set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating Python virtual environment..."
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
            PYTHON="$candidate"
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "Python 3.11 or newer is required" >&2
        exit 1
    fi
    "$PYTHON" -m venv .venv
fi

source .venv/bin/activate
echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet --editable ".[web]"

if [ ! -d web/frontend/node_modules ] || [ web/frontend/package.json -nt web/frontend/node_modules ]; then
    echo "Installing frontend dependencies..."
    (cd web/frontend && npm install && touch node_modules)
fi

echo "Starting backend on http://localhost:8000 ..."
uvicorn main:app --app-dir web/backend --reload --reload-dir web/backend --reload-dir src &
BACKEND_PID=$!

echo "Starting frontend on http://localhost:5173 ..."
(cd web/frontend && npm run dev) &
FRONTEND_PID=$!

trap 'echo "Shutting down..."; kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null' EXIT INT TERM

wait