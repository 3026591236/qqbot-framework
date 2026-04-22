#!/bin/sh
set -eu

APP_DIR=${1:-/opt/qqbot-framework}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PATH="/usr/local/sbin:/usr/local/bin:$PATH"
export PATH
PKG_MGR=""
SUDO=""
CAN_INSTALL_PKGS=0
LOGIN_MODE="qrcode"
PYTHON_BIN=""
OS_ID=""
OS_ID_LIKE=""

info() { printf '%s\n' "[INFO] $*"; }
warn() { printf '%s\n' "[WARN] $*"; }
ok() { printf '%s\n' "[ OK ] $*"; }
err() { printf '%s\n' "[ERR ] $*" >&2; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

read_user_input() {
  if [ -r /dev/tty ]; then
    IFS= read -r "$1" < /dev/tty || true
  else
    IFS= read -r "$1" || true
  fi
}

print_prompt() {
  if [ -w /dev/tty ]; then
    printf '%s' "$1" > /dev/tty
  else
    printf '%s' "$1"
  fi
}

ask() {
  prompt=$1
  default=${2:-}
  if [ -n "$default" ]; then
    print_prompt "$prompt [$default]: "
  else
    print_prompt "$prompt: "
  fi
  value=''
  read_user_input value
  if [ -z "$value" ]; then
    value=$default
  fi
  printf '%s' "$value"
}

ask_yes_no() {
  prompt=$1
  default=${2:-y}
  while :; do
    if [ "$default" = "y" ]; then
      print_prompt "$prompt [Y/n]: "
    else
      print_prompt "$prompt [y/N]: "
    fi
    answer=''
    read_user_input answer
    answer=$(printf '%s' "$answer" | tr 'A-Z' 'a-z')
    if [ -z "$answer" ]; then
      answer=$default
    fi
    case "$answer" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
    esac
    warn "请输入 y 或 n"
  done
}

trim() {
  printf '%s' "$1" | awk '{$1=$1};1'
}

detect_os() {
  if [ -f /etc/os-release ]; then
    OS_ID=$(sed -n 's/^ID=//p' /etc/os-release | head -n1 | tr -d '"')
    OS_ID_LIKE=$(sed -n 's/^ID_LIKE=//p' /etc/os-release | head -n1 | tr -d '"')
  fi
}

ensure_supported_os() {
  case "$OS_ID" in
    ubuntu|debian) return 0 ;;
  esac
  case " $OS_ID_LIKE " in
    *" debian "*) return 0 ;;
  esac
  err "当前安装器仅支持 Ubuntu / Debian 系统。检测到：ID=${OS_ID:-unknown} ID_LIKE=${OS_ID_LIKE:-unknown}"
  err "请改用 Ubuntu 22.04+ / Debian 12+，或手动部署。"
  exit 1
}

detect_pkg_manager() {
  if need_cmd apt-get; then PKG_MGR=apt
  else PKG_MGR=""
  fi
}

setup_privilege() {
  if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
    CAN_INSTALL_PKGS=1
    return
  fi
  if need_cmd sudo; then
    SUDO="sudo"
    CAN_INSTALL_PKGS=1
    return
  fi
  SUDO=""
  CAN_INSTALL_PKGS=0
}

port_in_use() {
  port=$1
  if need_cmd ss; then
    ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$port$"
    return $?
  fi
  if need_cmd netstat; then
    netstat -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$port$"
    return $?
  fi
  return 1
}

ensure_free_port() {
  name=$1
  default_port=$2
  port=$default_port
  while :; do
    port=$(ask "$name" "$port")
    port=$(trim "$port")
    case "$port" in
      ''|*[!0-9]*) warn "端口必须是数字"; port=$default_port; continue ;;
    esac
    if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
      warn "端口范围必须在 1-65535"
      port=$default_port
      continue
    fi
    if port_in_use "$port"; then
      warn "端口 $port 已被占用，请换一个"
      continue
    fi
    printf '%s' "$port"
    return
  done
}

install_packages() {
  [ $# -gt 0 ] || return 0
  if [ "$CAN_INSTALL_PKGS" -ne 1 ] || [ -z "$PKG_MGR" ]; then
    warn "当前无法自动安装依赖，请手动安装：$*"
    return 1
  fi
  info "尝试自动安装：$*"
  case "$PKG_MGR" in
    apt)
      $SUDO apt-get update
      $SUDO apt-get install -y "$@"
      ;;
    dnf)
      $SUDO dnf install -y "$@"
      ;;
    yum)
      $SUDO yum install -y "$@"
      ;;
    apk)
      $SUDO apk add --no-cache "$@"
      ;;
    *)
      warn "未知包管理器，无法自动安装：$*"
      return 1
      ;;
  esac
}

python_version_ge_310() {
  bin=$1
  "$bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

python_version_mm() {
  bin=$1
  "$bin" - <<'PY'
import sys
print(f"{sys.version_info[0]}.{sys.version_info[1]}")
PY
}

python_has_venv() {
  bin=$1
  "$bin" -m venv --help >/dev/null 2>&1
}

python_has_pip() {
  bin=$1
  "$bin" -m pip --version >/dev/null 2>&1
}

install_python_runtime_support() {
  bin=$1
  ver=$(python_version_mm "$bin")
  case "$PKG_MGR" in
    apt)
      case "$ver" in
        3.10)
          install_packages python3.10-venv python3-pip python3.10-distutils || true
          ;;
        3.11)
          install_packages python3.11-venv python3-pip python3.11-distutils || true
          ;;
        *)
          install_packages python3-venv python3-pip || true
          ;;
      esac
      ;;
  esac

  if ! python_has_pip "$bin"; then
    warn "$bin 仍缺少 pip，尝试使用 ensurepip"
    "$bin" -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi
}

select_python_bin() {
  for bin in \
    python3.11 \
    /usr/local/bin/python3.11 \
    python3.10 \
    /usr/local/bin/python3.10 \
    python3 \
    /usr/local/bin/python3
  do
    if [ -x "$bin" ] && python_version_ge_310 "$bin"; then
      PYTHON_BIN=$bin
      return 0
    fi
    if need_cmd "$bin" && python_version_ge_310 "$bin"; then
      PYTHON_BIN=$bin
      return 0
    fi
  done
  return 1
}

ensure_python_stack() {
  if ! select_python_bin; then
    warn "未检测到可用的 Python 3.10+，当前安装器不会使用 Python 3.6/3.7/3.8/3.9。"
    if need_cmd python3; then
      warn "当前系统默认 python3 版本：$(python3 --version 2>/dev/null || echo unknown)"
    fi
    info "尝试自动安装 Python 相关依赖"
    case "$PKG_MGR" in
      apt)
        install_packages python3 python3-venv python3-pip curl ca-certificates || true
        install_packages python3.10 python3.10-venv python3.10-distutils || true
        install_packages python3.11 python3.11-venv python3.11-distutils || true
        ;;
      dnf|yum)
        install_packages python3 python3-pip curl ca-certificates || true
        install_packages python3.10 python3.10-pip || true
        install_packages python3.11 python3.11-pip || true
        ;;
      apk)
        install_packages python3 py3-pip curl ca-certificates || true
        ;;
      *) warn "无法自动安装 Python 3.10+，请手动安装后重试" ;;
    esac
  fi

  select_python_bin || {
    err "未找到 Python 3.10+。请先安装 python3.10 或 python3.11，再重新运行安装器。"
    exit 1
  }

  if ! python_has_venv "$PYTHON_BIN" || ! python_has_pip "$PYTHON_BIN"; then
    warn "检测到 $PYTHON_BIN 缺少 venv 或 pip，尝试自动补装运行时组件"
    install_python_runtime_support "$PYTHON_BIN"
  fi

  python_has_venv "$PYTHON_BIN" || {
    err "$PYTHON_BIN 缺少 venv 支持，请先安装对应的 venv 包。"
    exit 1
  }
  python_has_pip "$PYTHON_BIN" || {
    err "$PYTHON_BIN 缺少 pip。"
    exit 1
  }
  ok "已选择 Python 解释器：$PYTHON_BIN ($($PYTHON_BIN --version 2>/dev/null))"
}

ensure_curl_or_wget() {
  if need_cmd curl || need_cmd wget; then
    return 0
  fi
  warn "未检测到 curl/wget"
  if ask_yes_no "是否尝试自动安装 curl？" "y"; then
    install_packages curl || true
  fi
}

ensure_docker_optional() {
  if need_cmd docker; then
    ok "已检测到 docker"
    return 0
  fi
  warn "未检测到 docker，NapCat 自动安装/启动将不可用"
  if ask_yes_no "是否尝试自动安装 Docker？" "n"; then
    case "$PKG_MGR" in
      apt) install_packages docker.io ;;
      dnf|yum) install_packages docker ;;
      apk) install_packages docker ;;
      *) warn "无法自动安装 docker，请自行安装" ;;
    esac
  fi
}

ensure_docker_running() {
  if ! need_cmd docker; then
    return 1
  fi
  if docker info >/dev/null 2>&1; then
    ok "Docker 服务可用"
    return 0
  fi
  warn "Docker 已安装，但服务似乎未启动"
  if need_cmd systemctl; then
    if ask_yes_no "是否尝试自动启动 Docker 服务？" "y"; then
      ${SUDO:-} systemctl enable docker >/dev/null 2>&1 || true
      ${SUDO:-} systemctl start docker >/dev/null 2>&1 || true
      sleep 2
      if docker info >/dev/null 2>&1; then
        ok "Docker 服务启动成功"
        return 0
      fi
    fi
  fi
  warn "Docker 服务仍不可用"
  return 1
}

choose_login_mode() {
  echo
  echo "请选择 QQ 登录方式："
  echo "  1) 扫码登录（推荐）"
  echo "  2) WebUI/链接登录（推荐）"
  echo "  3) QQ 密码登录（不支持自动化，不安全，不建议）"
  while :; do
    mode=$(ask "请输入编号" "1")
    case "$mode" in
      1) LOGIN_MODE="qrcode"; return ;;
      2) LOGIN_MODE="webui"; return ;;
      3)
        warn "不会把 QQ 明文密码写进安装脚本、配置文件或日志。当前安装器不支持密码登录自动化。"
        warn "建议改用：扫码登录 或 WebUI 链接登录。"
        ;;
      *) warn "请输入 1 / 2 / 3" ;;
    esac
  done
}

write_build_info() {
  BUILD_INFO_FILE="$APP_DIR/BUILD_INFO.json"
  BUILD_REPO=${QQBOT_BUILD_REPO:-3026591236/qqbot-framework}
  BUILD_BRANCH=${QQBOT_BUILD_BRANCH:-main}
  BUILD_COMMIT=${QQBOT_BUILD_COMMIT:-}
  BUILD_MODE=${QQBOT_BUILD_MODE:-local-copy}
  BUILD_VERSION=${QQBOT_BUILD_VERSION:-}
  BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)

  if [ -z "$BUILD_COMMIT" ] && command -v git >/dev/null 2>&1 && [ -d "$SRC_DIR/.git" ]; then
    BUILD_COMMIT=$(git -C "$SRC_DIR" rev-parse HEAD 2>/dev/null || true)
  fi
  if [ -z "$BUILD_VERSION" ] && [ -f "$SRC_DIR/VERSION" ]; then
    BUILD_VERSION=$(tr -d '\r' < "$SRC_DIR/VERSION" | head -n1)
  fi

  cat > "$BUILD_INFO_FILE" <<EOF
{
  "repo": "$BUILD_REPO",
  "branch": "$BUILD_BRANCH",
  "version": "$BUILD_VERSION",
  "commit": "$BUILD_COMMIT",
  "build_mode": "$BUILD_MODE",
  "build_time": "$BUILD_TIME"
}
EOF
  ok "构建信息已写入：$BUILD_INFO_FILE"
}

copy_project() {
  mkdir -p "$APP_DIR"
  info "复制项目到 $APP_DIR"
  tar \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='data' \
    --exclude='logs' \
    --exclude='ntqq' \
    --exclude='napcat/cache' \
    --exclude='build-release' \
    --exclude='build-release-zip' \
    --exclude='build-all-in-one' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.zip' \
    --exclude='*.tar.gz' \
    -cf - -C "$SRC_DIR" . | tar -xf - -C "$APP_DIR"
  chmod +x "$APP_DIR/run.sh" "$APP_DIR/deploy/install.sh" "$APP_DIR/deploy/bootstrap-install.sh" "$APP_DIR/install_plugin.py"
  mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$APP_DIR/ntqq" "$APP_DIR/napcat/config"
  write_build_info
  ok "项目已复制"
}

write_env() {
  ENV_FILE="$APP_DIR/.env"
  cat > "$ENV_FILE" <<EOF
QQBOT_APP_NAME=$APP_NAME
QQBOT_HOST=0.0.0.0
QQBOT_PORT=$APP_PORT
QQBOT_DEBUG=false
QQBOT_LOG_LEVEL=INFO
QQBOT_COMMAND_PREFIX=/
ONEBOT_API_BASE=http://127.0.0.1:$ONEBOT_PORT
QQBOT_DATA_DIR=./data
QQBOT_SQLITE_PATH=./data/qqbot.sqlite3
QQBOT_OWNER_IDS=$OWNER_QQ
QQBOT_MARKET_URL=
EOF
  ok ".env 已生成：$ENV_FILE"
}

write_service() {
  SERVICE_FILE="$APP_DIR/deploy/qqbot-framework.service"
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=QQ Bot Framework
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/run.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  ok "systemd 服务文件已生成：$SERVICE_FILE"
}

upgrade_pip_tooling() {
  if python -m pip install --upgrade pip setuptools wheel; then
    return 0
  fi
  warn "默认 pip 源升级 pip/setuptools/wheel 失败，尝试官方 PyPI"
  python -m pip install -i https://pypi.org/simple --upgrade pip setuptools wheel
}

pip_install_with_fallback() {
  req_file=$1

  if python -m pip install -r "$req_file"; then
    return 0
  fi

  warn "默认 pip 源安装失败，尝试先升级 pip 工具链后重试"
  upgrade_pip_tooling || true
  if python -m pip install -r "$req_file"; then
    return 0
  fi

  warn "默认 pip 源仍失败，切换到官方 PyPI 源重试"
  if python -m pip install -i https://pypi.org/simple -r "$req_file"; then
    return 0
  fi

  warn "官方 PyPI 仍失败，再次升级 pip 工具链并最后重试一次"
  upgrade_pip_tooling
  python -m pip install -i https://pypi.org/simple -r "$req_file"
}

install_python_env() {
  info "创建 Python 虚拟环境并安装依赖"
  [ -d "$APP_DIR/.venv" ] || "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
  . "$APP_DIR/.venv/bin/activate"
  upgrade_pip_tooling
  pip_install_with_fallback "$APP_DIR/requirements.txt"
  ok "Python 依赖安装完成"
}

write_napcat_config() {
  mkdir -p "$APP_DIR/napcat/config"
  ACCOUNT_CONFIG="$APP_DIR/napcat/config/onebot11_${NAPCAT_ACCOUNT}.json"
  cat > "$ACCOUNT_CONFIG" <<EOF
{
  "network": {
    "httpServers": [
      {
        "enable": true,
        "name": "qqbot-http-server",
        "host": "0.0.0.0",
        "port": $ONEBOT_PORT,
        "enableCors": true,
        "enableWebsocket": false,
        "messagePostFormat": "string",
        "token": "",
        "debug": false
      }
    ],
    "httpSseServers": [],
    "httpClients": [
      {
        "enable": true,
        "name": "qqbot-http-client",
        "url": "http://host.docker.internal:$APP_PORT/onebot/event",
        "reportSelfMessage": false,
        "messagePostFormat": "string",
        "token": "",
        "debug": false
      }
    ],
    "websocketServers": [],
    "websocketClients": [],
    "plugins": []
  },
  "musicSignUrl": "",
  "enableLocalFile2Url": false,
  "parseMultMsg": false,
  "imageDownloadProxy": "",
  "timeout": {
    "baseTimeout": 10000,
    "uploadSpeedKBps": 256,
    "downloadSpeedKBps": 256,
    "maxTimeout": 1800000
  }
}
EOF
  ok "NapCat OneBot 配置已生成：$ACCOUNT_CONFIG"
}

install_systemd_service() {
  if ! need_cmd systemctl; then
    warn "未检测到 systemctl，跳过 systemd 安装"
    return 0
  fi
  if [ "$(id -u)" -ne 0 ]; then
    warn "当前不是 root，无法自动安装到 /etc/systemd/system"
    warn "你可以手动复制：$APP_DIR/deploy/qqbot-framework.service"
    return 0
  fi
  cp "$APP_DIR/deploy/qqbot-framework.service" /etc/systemd/system/qqbot-framework.service
  systemctl daemon-reload
  systemctl enable qqbot-framework >/dev/null 2>&1 || true
  ok "systemd 服务已安装：qqbot-framework"
}

start_framework_systemd() {
  systemctl restart qqbot-framework
  sleep 2
}

start_framework_nohup() {
  info "使用 nohup 启动 qqbot-framework"
  mkdir -p "$APP_DIR/logs"
  if pgrep -f "$APP_DIR/.venv/bin/uvicorn app.main:app" >/dev/null 2>&1; then
    warn "检测到已有 qqbot-framework 进程，跳过重复启动"
    return 0
  fi
  (
    cd "$APP_DIR"
    nohup "$APP_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$APP_PORT" > "$APP_DIR/logs/uvicorn.log" 2>&1 < /dev/null &
  )
  sleep 2
  ok "框架已后台启动，日志：$APP_DIR/logs/uvicorn.log"
}

show_napcat_runtime_hint() {
  if ! need_cmd docker; then
    return 0
  fi
  echo
  echo "================ NapCat 登录入口 ================"
  echo "WebUI 本机地址 : http://127.0.0.1:$NAPCAT_WEBUI_PORT/webui"
  for ip in $(hostname -I 2>/dev/null || true); do
    [ -n "$ip" ] || continue
    echo "WebUI 外部地址 : http://$ip:$NAPCAT_WEBUI_PORT/webui"
  done
  echo "查看实时日志   : docker logs -f napcat"
  echo "最近日志预览   :"
  docker logs --tail 60 napcat 2>/dev/null || true
  echo "==============================================="
  echo
}

start_napcat_docker() {
  if ! need_cmd docker; then
    warn "未检测到 docker，跳过 NapCat 启动"
    return 0
  fi
  ensure_docker_running || true
  if ! docker info >/dev/null 2>&1; then
    warn "Docker 服务不可用，无法启动 NapCat"
    return 0
  fi
  if docker ps -a --format '{{.Names}}' | grep -qx 'napcat'; then
    warn "检测到已有名为 napcat 的容器，将尝试直接启动"
    docker start napcat >/dev/null 2>&1 || true
    sleep 3
    show_napcat_runtime_hint
    return 0
  fi
  info "拉起 NapCat 容器"
  docker run -d \
    --name napcat \
    --restart always \
    -e NAPCAT_UID=0 \
    -e NAPCAT_GID=0 \
    -e ACCOUNT="$NAPCAT_ACCOUNT" \
    -p "$ONEBOT_PORT:$ONEBOT_PORT" \
    -p "$NAPCAT_WEBUI_PORT:$NAPCAT_WEBUI_PORT" \
    --add-host host.docker.internal:host-gateway \
    -v "$APP_DIR/napcat/config:/app/napcat/config" \
    -v "$APP_DIR/ntqq:/app/.config/QQ" \
    mlikiowa/napcat-docker:latest >/dev/null
  ok "NapCat 已启动"
  sleep 5
  show_napcat_runtime_hint
}

check_framework_health() {
  if need_cmd curl; then
    curl -fsS "http://127.0.0.1:$APP_PORT/healthz" >/dev/null 2>&1
    return $?
  fi
  return 1
}

check_napcat_health() {
  if need_cmd curl; then
    curl -fsS -X POST "http://127.0.0.1:$ONEBOT_PORT/get_status" >/dev/null 2>&1
    return $?
  fi
  return 1
}

show_env_report() {
  echo
  echo "================ 环境检测 ================"
  echo "系统       : $(uname -srm 2>/dev/null || echo unknown)"
  echo "OS ID      : ${OS_ID:-unknown}"
  echo "OS LIKE    : ${OS_ID_LIKE:-unknown}"
  echo "安装目录   : $APP_DIR"
  echo "root身份   : $( [ "$(id -u)" -eq 0 ] && echo yes || echo no )"
  echo "sudo可用   : $( need_cmd sudo && echo yes || echo no )"
  echo "包管理器   : ${PKG_MGR:-unknown}"
  echo "python3    : $( command -v python3 2>/dev/null || echo missing )"
  echo "python3.10 : $( command -v python3.10 2>/dev/null || [ -x /usr/local/bin/python3.10 ] && echo /usr/local/bin/python3.10 || echo missing )"
  echo "python3.11 : $( command -v python3.11 2>/dev/null || [ -x /usr/local/bin/python3.11 ] && echo /usr/local/bin/python3.11 || echo missing )"
  echo "docker     : $( command -v docker 2>/dev/null || echo missing )"
  echo "systemctl  : $( command -v systemctl 2>/dev/null || echo missing )"
  echo "curl/wget  : $( (command -v curl || command -v wget) 2>/dev/null | head -n1 || echo missing )"
  echo "=========================================="
  echo
}

show_login_hint() {
  echo
  echo "================ QQ 登录指引 ================"
  case "$LOGIN_MODE" in
    qrcode)
      echo "你选择了：扫码登录"
      echo "请执行查看日志：docker logs -f napcat"
      echo "NapCat WebUI：http://127.0.0.1:$NAPCAT_WEBUI_PORT/webui"
      echo "如果日志中出现二维码或链接，直接扫码即可。"
      ;;
    webui)
      echo "你选择了：WebUI / 链接登录"
      echo "请打开：http://127.0.0.1:$NAPCAT_WEBUI_PORT/webui"
      echo "进入后按页面提示进行链接登录/扫码登录。"
      echo "如果需要 token，请查看：docker logs -f napcat"
      ;;
  esac
  echo "当前安装器不支持 QQ 明文密码自动登录。"
  echo "============================================"
}

print_summary() {
  echo
  echo "================ 安装完成 ================"
  echo "项目目录      : $APP_DIR"
  echo "机器人名称    : $APP_NAME"
  echo "主人QQ        : $OWNER_QQ"
  echo "框架端口      : $APP_PORT"
  echo "OneBot端口    : $ONEBOT_PORT"
  echo "NapCat WebUI  : $NAPCAT_WEBUI_PORT"
  echo "Python解释器  : $PYTHON_BIN"
  echo
  echo "关键文件："
  echo "- 配置文件     : $APP_DIR/.env"
  echo "- 服务文件     : $APP_DIR/deploy/qqbot-framework.service"
  echo "- NapCat配置   : $APP_DIR/napcat/config/onebot11_${NAPCAT_ACCOUNT}.json"
  echo
  echo "检查命令："
  echo "- 框架健康检查 : curl http://127.0.0.1:$APP_PORT/healthz"
  echo "- NapCat状态   : curl -X POST http://127.0.0.1:$ONEBOT_PORT/get_status"
  echo "- NapCat WebUI : http://127.0.0.1:$NAPCAT_WEBUI_PORT/webui"
  echo
  echo "文档入口："
  echo "- $APP_DIR/README.md"
  echo "- $APP_DIR/docs/DEPLOY_GUIDE.md"
  echo "- $APP_DIR/deploy/NAPCAT_DEPLOY.md"
  echo "- $APP_DIR/docs/PLUGIN_GUIDE.md"
  echo "=========================================="
}

info "启动 QQ Bot Framework 安装器"
detect_os
ensure_supported_os
detect_pkg_manager
setup_privilege
ensure_curl_or_wget
ensure_python_stack
ensure_docker_optional
show_env_report

APP_NAME=$(ask "机器人名称" "QQ Bot Framework")
OWNER_QQ=$(trim "$(ask "请输入主人 QQ" "")")
while [ -z "$OWNER_QQ" ]; do
  warn "主人 QQ 不能为空"
  OWNER_QQ=$(trim "$(ask "请输入主人 QQ" "")")
done
APP_PORT=$(ensure_free_port "框架监听端口" "9000")
ONEBOT_PORT=$(ensure_free_port "NapCat OneBot API 端口" "3000")
NAPCAT_WEBUI_PORT=$(ensure_free_port "NapCat WebUI 端口" "6099")
NAPCAT_ACCOUNT=$(trim "$(ask "NapCat 登录 QQ 号（默认同主人QQ）" "$OWNER_QQ")")
[ -n "$NAPCAT_ACCOUNT" ] || NAPCAT_ACCOUNT="$OWNER_QQ"
choose_login_mode

copy_project
write_env
write_service

if ask_yes_no "现在安装 Python 依赖并初始化运行环境？" "y"; then
  install_python_env
fi

if ask_yes_no "是否安装 systemd 服务文件？" "y"; then
  install_systemd_service || true
fi

if ask_yes_no "是否生成 NapCat 配置？" "y"; then
  write_napcat_config
fi

if ask_yes_no "如果已安装 Docker，是否现在启动 NapCat？" "y"; then
  start_napcat_docker || true
fi

if ask_yes_no "是否现在启动 qqbot-framework？" "y"; then
  if need_cmd systemctl && [ "$(id -u)" -eq 0 ]; then
    start_framework_systemd || true
  else
    start_framework_nohup || true
  fi
fi

info "执行安装后健康检查"
if check_framework_health; then
  ok "qqbot-framework 健康检查通过"
else
  warn "qqbot-framework 健康检查未通过，请检查日志或依赖安装情况"
fi

if check_napcat_health; then
  ok "NapCat HTTP API 健康检查通过"
else
  warn "NapCat HTTP API 暂未通过检查（如果你还没完成登录，这很正常）"
fi

show_login_hint
print_summary
