#!/bin/bash
# User Feedback Discovery Engine Launcher
set -euo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Fail fast: the Gemini key must come from the server environment.
# Fall back to .streamlit/secrets.toml if it defines GEMINI_API_KEY.
if [ -z "${GEMINI_API_KEY:-}" ] && [ -f ".streamlit/secrets.toml" ]; then
    if grep -qE '^[[:space:]]*GEMINI_API_KEY[[:space:]]*=' .streamlit/secrets.toml; then
        GEMINI_API_KEY="$(sed -nE 's/^[[:space:]]*GEMINI_API_KEY[[:space:]]*=[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/p' .streamlit/secrets.toml | head -1)"
        export GEMINI_API_KEY
    fi
fi

if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "ERROR: GEMINI_API_KEY is not set." >&2
    echo >&2
    echo "This app reads the Google Gemini API key from the server environment." >&2
    echo "Set it and try again:" >&2
    echo >&2
    echo "    export GEMINI_API_KEY=\"your-key-here\"" >&2
    echo "    ./run.sh" >&2
    echo >&2
    echo "Or add it to .streamlit/secrets.toml (see .streamlit/secrets.toml.example)." >&2
    exit 1
fi

# Ensure venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
fi

echo "Starting User Feedback Discovery Engine..."
exec ./venv/bin/streamlit run app.py "$@"
