#!/bin/sh
set -eu

# 用法示例：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/bootstrap-install.sh | \
#     REPO_OWNER=<owner> REPO_NAME=<repo> REPO_REF=<branch> sh

REPO_OWNER=${REPO_OWNER:-}
REPO_NAME=${REPO_NAME:-}
REPO_REF=${REPO_REF:-main}
APP_DIR=${APP_DIR:-/opt/qqbot-framework}
WORKDIR=${WORKDIR:-/tmp/qqbot-framework-bootstrap}

info() { printf '%s\n' "[INFO] $*"; }
warn() { printf '%s\n' "[WARN] $*"; }
ok() { printf '%s\n' "[ OK ] $*"; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

fetch() {
  url=$1
  out=$2
  if need_cmd curl; then
    curl -fsSL "$url" -o "$out"
    return 0
  fi
  if need_cmd wget; then
    wget -qO "$out" "$url"
    return 0
  fi
  warn "未检测到 curl 或 wget，无法下载 GitHub 仓库"
  return 1
}

fetch_text() {
  url=$1
  if need_cmd curl; then
    curl -fsSL "$url"
    return 0
  fi
  if need_cmd wget; then
    wget -qO- "$url"
    return 0
  fi
  return 1
}

fetch_commit_sha() {
  api_url="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/commits/${REPO_REF}"
  json=$(fetch_text "$api_url" 2>/dev/null || true)
  if [ -n "$json" ]; then
    printf '%s' "$json" | sed -n 's/.*"sha"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F]\{40\}\)".*/\1/p' | head -n1
  fi
}

if [ -z "$REPO_OWNER" ] || [ -z "$REPO_NAME" ]; then
  warn "请先设置 REPO_OWNER 和 REPO_NAME"
  warn "示例：REPO_OWNER=3026591236 REPO_NAME=qqbot-framework REPO_REF=main sh bootstrap-install.sh"
  exit 1
fi

if ! need_cmd tar; then
  warn "未检测到 tar，请先安装 tar"
  exit 1
fi

ARCHIVE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${REPO_REF}.tar.gz"
ARCHIVE_FILE="${WORKDIR}/repo.tar.gz"
EXTRACT_DIR="${WORKDIR}/src"

info "QQ Bot Framework 远程安装引导"
info "仓库：${REPO_OWNER}/${REPO_NAME}"
info "分支：${REPO_REF}"
info "安装目录：${APP_DIR}"
info "源码下载地址：${ARCHIVE_URL}"

BUILD_COMMIT=$(fetch_commit_sha || true)
if [ -n "$BUILD_COMMIT" ]; then
  info "检测到远端提交：${BUILD_COMMIT}"
fi

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR" "$EXTRACT_DIR"

fetch "$ARCHIVE_URL" "$ARCHIVE_FILE"
ok "仓库压缩包下载完成"

tar -xzf "$ARCHIVE_FILE" -C "$EXTRACT_DIR"
ok "源码解压完成"

SRC_DIR=$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)
if [ -z "$SRC_DIR" ]; then
  warn "未找到解压后的源码目录"
  exit 1
fi

if [ ! -f "$SRC_DIR/deploy/install.sh" ]; then
  warn "源码中未找到 deploy/install.sh"
  exit 1
fi

chmod +x "$SRC_DIR/deploy/install.sh"
info "即将进入交互式安装流程..."
export QQBOT_BUILD_REPO="${REPO_OWNER}/${REPO_NAME}"
export QQBOT_BUILD_BRANCH="${REPO_REF}"
export QQBOT_BUILD_COMMIT="${BUILD_COMMIT:-}"
export QQBOT_BUILD_VERSION="$(tr -d '\r' < "$SRC_DIR/VERSION" 2>/dev/null | head -n1 || true)"
export QQBOT_BUILD_MODE="archive"
exec "$SRC_DIR/deploy/install.sh" "$APP_DIR"
