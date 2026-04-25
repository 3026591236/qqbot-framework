#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p logs

pkill -f '.venv/bin/uvicorn app.openclaw_bridge_server:app' || true
nohup "$ROOT_DIR/scripts/run_openclaw_bridge.sh" > "$ROOT_DIR/logs/openclaw-bridge.out" 2>&1 < /dev/null &
echo $! > "$ROOT_DIR/logs/openclaw-bridge.pid"
echo "started pid=$(cat "$ROOT_DIR/logs/openclaw-bridge.pid")"
