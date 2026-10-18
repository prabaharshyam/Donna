#!/bin/bash
# Start Donna locally → http://localhost:8765
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt
fi
export TZ="${TZ:-Asia/Kolkata}"
exec .venv/bin/uvicorn server.app:app --host 127.0.0.1 --port "${PORT:-8765}" "$@"
