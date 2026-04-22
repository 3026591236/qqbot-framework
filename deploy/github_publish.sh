#!/bin/sh
set -eu

# 安全用法：
# 1) 先在服务器本地准备 token（不要发到聊天里）
#    mkdir -p ~/.config/qqbot-framework
#    printf '%s' 'ghp_xxx' > ~/.config/qqbot-framework/github_token
#    chmod 600 ~/.config/qqbot-framework/github_token
#
# 2) 执行：
#    GITHUB_REPO='你的用户名/仓库名' \
#    GIT_USER_NAME='你的GitHub用户名' \
#    GIT_USER_EMAIL='你的邮箱' \
#    ./deploy/github_publish.sh
#
# 可选环境变量：
#   REPO_DIR       默认当前项目根目录
#   BRANCH         默认 main
#   COMMIT_MESSAGE 默认 "Open source release"
#   TOKEN_FILE     默认 ~/.config/qqbot-framework/github_token

REPO_DIR=${REPO_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
BRANCH=${BRANCH:-main}
COMMIT_MESSAGE=${COMMIT_MESSAGE:-Open source release}
TOKEN_FILE=${TOKEN_FILE:-$HOME/.config/qqbot-framework/github_token}
GITHUB_REPO=${GITHUB_REPO:-}
GIT_USER_NAME=${GIT_USER_NAME:-}
GIT_USER_EMAIL=${GIT_USER_EMAIL:-}

info() { printf '%s\n' "[INFO] $*"; }
warn() { printf '%s\n' "[WARN] $*"; }
ok()   { printf '%s\n' "[ OK ] $*"; }
need() { command -v "$1" >/dev/null 2>&1; }

if [ -z "$GITHUB_REPO" ] || [ -z "$GIT_USER_NAME" ] || [ -z "$GIT_USER_EMAIL" ]; then
  warn "缺少必要环境变量。"
  warn "需要：GITHUB_REPO, GIT_USER_NAME, GIT_USER_EMAIL"
  exit 1
fi

if [ ! -f "$TOKEN_FILE" ]; then
  warn "未找到 token 文件：$TOKEN_FILE"
  warn "请先在服务器本地创建它，并 chmod 600。"
  exit 1
fi

if ! need git; then
  warn "未检测到 git"
  exit 1
fi

TOKEN=$(cat "$TOKEN_FILE")
if [ -z "$TOKEN" ]; then
  warn "token 文件为空"
  exit 1
fi

cd "$REPO_DIR"

info "准备公开仓库内容（移除不应提交的已跟踪运行文件）"
git init >/dev/null 2>&1 || true
git config user.name "$GIT_USER_NAME"
git config user.email "$GIT_USER_EMAIL"

# 清掉可能已被跟踪、但不该公开的运行文件/目录
for path in \
  .env \
  data \
  logs \
  ntqq \
  napcat/cache \
  napcat/config/onebot11_3837772523.json \
  napcat/config/onebot11_qqbot.json \
  napcat/config/napcat.json \
  napcat/config/napcat_3837772523.json \
  napcat/config/napcat_protocol_3837772523.json \
  napcat/config/webui.json \
  qqbot-framework-release.tar.gz \
  qqbot-framework-release.zip \
  qqbot-framework-all-in-one.zip \
  'QQ机器人完整部署包.zip' \
  build-release \
  build-release-zip \
  build-all-in-one
  do
  git rm -r --cached --ignore-unmatch "$path" >/dev/null 2>&1 || true
done

# 清缓存文件
find . -type d -name '__pycache__' -prune -exec git rm -r --cached --ignore-unmatch {} + >/dev/null 2>&1 || true
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -exec git rm --cached --ignore-unmatch {} + >/dev/null 2>&1 || true

# 正常提交公开内容
git add .
if git diff --cached --quiet; then
  warn "没有可提交的变更。"
else
  git commit -m "$COMMIT_MESSAGE"
  ok "本地提交完成"
fi

REMOTE_URL="https://github.com/${GITHUB_REPO}.git"
AUTH_HEADER=$(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

info "推送到 GitHub：$GITHUB_REPO"
git -c http.extraHeader="Authorization: Basic $AUTH_HEADER" push -u origin HEAD:"$BRANCH"
ok "推送完成：https://github.com/${GITHUB_REPO}"
