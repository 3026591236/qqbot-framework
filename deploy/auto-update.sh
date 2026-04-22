#!/bin/sh
set -eu

BRANCH=${1:-main}
TARGET_SHA=${2:-}
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RESULT_FILE="$BASE_DIR/data/update_checker_result.json"
BUILD_INFO_FILE="$BASE_DIR/BUILD_INFO.json"
VERSION_FILE="$BASE_DIR/VERSION"

now_utc() {
  date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date
}

write_result() {
  ok=$1
  old_sha=$2
  new_sha=$3
  err_msg=${4:-}
  cat > "$RESULT_FILE" <<EOF
{
  "ok": $ok,
  "branch": "$BRANCH",
  "old_sha": "$old_sha",
  "new_sha": "$new_sha",
  "error": $(printf '%s' "$err_msg" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
  "finished_at": "$(now_utc)",
  "notified": false
}
EOF
}

cd "$BASE_DIR"
OLD_SHA=$(git rev-parse HEAD 2>/dev/null || true)

if ! git fetch origin; then
  write_result false "$OLD_SHA" "$OLD_SHA" "git fetch 失败"
  exit 1
fi

if ! git checkout "$BRANCH"; then
  write_result false "$OLD_SHA" "$OLD_SHA" "git checkout 失败"
  exit 1
fi

if ! git pull --ff-only origin "$BRANCH"; then
  write_result false "$OLD_SHA" "$OLD_SHA" "git pull 失败"
  exit 1
fi

NEW_SHA=$(git rev-parse HEAD 2>/dev/null || true)
if [ -n "$TARGET_SHA" ] && [ "$NEW_SHA" != "$TARGET_SHA" ]; then
  write_result false "$OLD_SHA" "$NEW_SHA" "更新后的提交与目标版本不一致"
  exit 1
fi

BUILD_VERSION=""
if [ -f "$VERSION_FILE" ]; then
  BUILD_VERSION=$(tr -d '\r' < "$VERSION_FILE" | head -n1)
fi

cat > "$BUILD_INFO_FILE" <<EOF
{
  "repo": "3026591236/qqbot-framework",
  "branch": "$BRANCH",
  "version": "$BUILD_VERSION",
  "commit": "$NEW_SHA",
  "build_mode": "git-auto-update",
  "build_time": "$(now_utc)"
}
EOF

write_result true "$OLD_SHA" "$NEW_SHA" ""

if [ -f "$BASE_DIR/.venv/bin/pip" ]; then
  "$BASE_DIR/.venv/bin/pip" install -r "$BASE_DIR/requirements.txt" >/dev/null 2>&1 || true
fi

SERVICE_NAME="${QQBOT_SYSTEMD_SERVICE:-qqbot-framework}"
if [ -n "$SERVICE_NAME" ] && command -v systemctl >/dev/null 2>&1 && systemctl status "$SERVICE_NAME" >/dev/null 2>&1; then
  systemctl restart "$SERVICE_NAME"
  exit 0
fi

PID=$(pgrep -f "$BASE_DIR/.venv/bin/uvicorn app.main:app" | head -n1 || true)
if [ -n "$PID" ]; then
  kill "$PID" || true
  sleep 2
fi
nohup "$BASE_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port "${QQBOT_PORT:-9000}" > "$BASE_DIR/logs/uvicorn.log" 2>&1 < /dev/null &
