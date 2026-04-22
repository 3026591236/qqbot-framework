#!/bin/sh
set -eu

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
pip install -r requirements.txt
mkdir -p "${QQBOT_DATA_DIR:-./data}"
exec uvicorn app.main:app --host "${QQBOT_HOST:-0.0.0.0}" --port "${QQBOT_PORT:-9000}"
