#!/bin/sh
set -eu

# 用法示例：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/bootstrap-git-install.sh | \
#     REPO_OWNER=<owner> REPO_NAME=<repo> REPO_REF=<branch> APP_DIR=/opt/qqbot-framework sh

REPO_OWNER=${REPO_OWNER:-}
REPO_NAME=${REPO_NAME:-}
REPO_REF=${REPO_REF:-main}
APP_DIR=${APP_DIR:-/opt/qqbot-framework}
GIT_CLONE_URL=${GIT_CLONE_URL:-}

info() { printf '%s\n' "[INFO] $*"; }
warn() { printf '%s\n' "[WARN] $*"; }
ok() { printf '%s\n' "[ OK ] $*"; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

if [ -z "$REPO_OWNER" ] || [ -z "$REPO_NAME" ]; then
  warn "请先设置 REPO_OWNER 和 REPO_NAME"
  warn "示例：REPO_OWNER=3026591236 REPO_NAME=qqbot-framework REPO_REF=main sh bootstrap-git-install.sh"
  exit 1
fi

if ! need_cmd git; then
  warn "未检测到 git，请先安装 git 后重试。"
  exit 1
fi

REPO_URL=${GIT_CLONE_URL:-"https://github.com/${REPO_OWNER}/${REPO_NAME}.git"}
PARENT_DIR=$(dirname "$APP_DIR")
APP_NAME=$(basename "$APP_DIR")

info "QQ Bot Framework Git 一键安装"
info "仓库：${REPO_OWNER}/${REPO_NAME}"
info "分支：${REPO_REF}"
info "安装目录：${APP_DIR}"
info "仓库地址：${REPO_URL}"
info "提示：国内机器可通过 GIT_CLONE_URL 指向镜像 git 地址"

mkdir -p "$PARENT_DIR"

if [ -d "$APP_DIR/.git" ]; then
  info "检测到已有 git 工作区，尝试更新到最新代码"
  git -C "$APP_DIR" fetch origin
  git -C "$APP_DIR" checkout "$REPO_REF"
  git -C "$APP_DIR" pull --ff-only origin "$REPO_REF"
else
  if [ -d "$APP_DIR" ] && [ "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]; then
    warn "目标目录已存在且非空：$APP_DIR"
    warn "为避免覆盖现有文件，请先清空目录或更换 APP_DIR。"
    exit 1
  fi
  rm -rf "$APP_DIR"
  git clone --branch "$REPO_REF" --single-branch "$REPO_URL" "$APP_DIR"
fi

ok "源码已准备完成（git 工作区保留）"

if [ ! -f "$APP_DIR/deploy/install.sh" ]; then
  warn "仓库中未找到 deploy/install.sh"
  exit 1
fi

chmod +x "$APP_DIR/deploy/install.sh"
export QQBOT_BUILD_REPO="${REPO_OWNER}/${REPO_NAME}"
export QQBOT_BUILD_BRANCH="${REPO_REF}"
export QQBOT_BUILD_COMMIT="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)"
export QQBOT_BUILD_VERSION="$(tr -d '\r' < "$APP_DIR/VERSION" 2>/dev/null | head -n1 || true)"
export QQBOT_BUILD_MODE="git"
info "即将进入交互式安装流程..."
exec "$APP_DIR/deploy/install.sh" "$APP_DIR"
