#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

if [ ! -x .venv/bin/uvicorn ]; then
  . .venv/bin/activate
  pip install -r requirements.txt
fi

export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

HOST="${QQBOT_OPENCLAW_BRIDGE_HOST:-0.0.0.0}"
PORT="${QQBOT_OPENCLAW_BRIDGE_PORT:-3001}"

exec .venv/bin/uvicorn app.openclaw_bridge_server:app --host "$HOST" --port "$PORT"
