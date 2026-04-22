#!/bin/sh
set -eu

BASE_URL=${1:-http://127.0.0.1:9000}
API_URL=${2:-http://127.0.0.1:5700}

echo "[1/2] Checking framework health: $BASE_URL/healthz"
curl -fsS "$BASE_URL/healthz" && echo

echo "[2/2] Checking OneBot API reachability: $API_URL"
curl -fsS "$API_URL" >/dev/null 2>&1 || true

echo "Framework reachable. If OneBot root path has no response, check adapter-specific health/API endpoint manually."
