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

for var in APP_USERNAME APP_PASSWORD; do
    if [ -z "${!var:-}" ]; then
        echo "ERROR: $var is not set." >&2
        echo >&2
        echo "Login credentials are read from the server environment:" >&2
        echo >&2
        echo "    export APP_USERNAME=\"your-username\"" >&2
        echo "    export APP_PASSWORD=\"your-password\"" >&2
        echo "    export APP_SECRET_KEY=\"\$(python3 -c 'import secrets;print(secrets.token_hex(32))')\"" >&2
        echo "    ./run.sh" >&2
        exit 1
    fi
done

if [ -z "${APP_SECRET_KEY:-}" ]; then
    echo "WARNING: APP_SECRET_KEY is not set; a random key will be generated per" >&2
    echo "         process, so all sessions are invalidated when the app restarts." >&2
fi

# Ensure venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
fi

echo "Starting User Feedback Discovery Engine..."
exec ./venv/bin/streamlit run app.py "$@"
