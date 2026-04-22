# 部署指南

本文档给出 `qqbot-framework` 的推荐部署方式、最小依赖、启动流程、NapCat 对接方式、systemd 托管方式与迁移注意事项。

## 1. 推荐架构

当前实际验证通过的推荐架构：

```text
QQ ←→ NapCat ←→ OneBot HTTP API / HTTP 回调 ←→ qqbot-framework
```

其中：

- `NapCat` 负责 QQ 登录、在线状态维护、收发 QQ 消息
- `qqbot-framework` 负责插件系统、命令处理、积分、签到、群管等业务

## 2. 运行环境要求

### 必需

- Linux 服务器 / VPS / 本地 Linux 主机
- Python 3.10+
- `python3 -m venv`
- `pip`

### 推荐

- Docker
- `docker-compose`（可选，旧版也可不用）
- systemd

## 3. 默认端口

- `9000`：qqbot-framework Web 服务
- `3000`：NapCat OneBot HTTP API
- `6099`：NapCat WebUI

如果这些端口有冲突，请自行修改配置并同步调整文档中的 URL。

## 4. 目录说明

推荐解压后目录类似：

```text
qqbot-framework/
├── app/
├── data/
├── deploy/
├── docs/
├── logs/
├── napcat/
├── ntqq/
├── user_plugins/
├── .env
├── .env.example
├── run.sh
└── install_plugin.py
```

说明：

- `app/`：框架主代码
- `data/`：SQLite 数据、插件注册信息
- `deploy/`：部署模板、systemd、NapCat 配置示例
- `docs/`：项目文档
- `logs/`：运行日志（如你自行重定向）
- `napcat/`：NapCat 配置目录
- `ntqq/`：NapCat / QQ 登录态目录
- `user_plugins/`：你的自定义插件目录

## 5. 部署 qqbot-framework

### 5.0 Git 工作区部署（推荐给需要更新检测 / git pull 更新的人）

如果你希望部署后保留 `.git`，并完整支持：

- `检查更新`
- `更新状态`
- 自动提醒新版本
- 后续 `git pull` 更新

推荐直接使用 Git 工作区安装：

```bash
curl -fsSL https://raw.githubusercontent.com/3026591236/qqbot-framework/main/deploy/bootstrap-git-install.sh | \
  REPO_OWNER=3026591236 REPO_NAME=qqbot-framework REPO_REF=main APP_DIR=/opt/qqbot-framework sh
```

说明：

- 该脚本会直接 `git clone` 仓库
- 保留 `.git` 目录
- 然后继续调用现有安装器 `deploy/install.sh`
- 比 archive / 解压式安装更适合长期维护

### 5.1 解压

```bash
mkdir -p /opt/qqbot-framework
cd /opt/qqbot-framework
tar -xzf qqbot-framework-release.tar.gz
```

### 5.2 配置环境变量

```bash
cp .env.example .env
```

至少需要修改：

```env
ONEBOT_API_BASE=http://127.0.0.1:3000
QQBOT_OWNER_IDS=你的QQ号
```

可选常用项：

```env
QQBOT_APP_NAME=QQ Bot Framework
QQBOT_HOST=0.0.0.0
QQBOT_PORT=9000
QQBOT_LOG_LEVEL=INFO
QQBOT_COMMAND_PREFIX=/
QQBOT_DATA_DIR=./data
QQBOT_SQLITE_PATH=./data/qqbot.sqlite3
QQBOT_MARKET_URL=
```

### 5.3 启动框架

```bash
chmod +x run.sh
./run.sh
```

默认行为：

- 若 `.venv` 不存在会自动创建
- 自动安装 `requirements.txt`
- 启动 `uvicorn app.main:app`

### 5.4 健康检查

```bash
curl http://127.0.0.1:9000/healthz
```

预期返回：

```json
{"ok":true}
```

## 6. 部署 NapCat

推荐直接看：

- `deploy/NAPCAT_DEPLOY.md`
- `deploy/docker-compose.napcat.yml`
- `deploy/napcat.onebot11.template.json`

这里给最短流程。

### 6.1 准备目录

```bash
mkdir -p napcat/config ntqq
```

### 6.2 启动 NapCat

```bash
docker run -d \
  --name napcat \
  --restart always \
  -e NAPCAT_UID=0 \
  -e NAPCAT_GID=0 \
  -e ACCOUNT=你的QQ号 \
  -p 3000:3000 \
  -p 6099:6099 \
  --add-host host.docker.internal:host-gateway \
  -v $(pwd)/napcat/config:/app/napcat/config \
  -v $(pwd)/ntqq:/app/.config/QQ \
  mlikiowa/napcat-docker:latest
```

### 6.3 配置对接关系

要确保 NapCat：

- HTTP API 对外：`http://127.0.0.1:3000`
- HTTP 上报地址：`http://host.docker.internal:9000/onebot/event`

对应框架 `.env`：

```env
ONEBOT_API_BASE=http://127.0.0.1:3000
```

### 6.4 扫码登录

查看日志：

```bash
docker logs -f napcat
```

登录成功后可验证：

```bash
curl -X POST http://127.0.0.1:3000/get_login_info
curl -X POST http://127.0.0.1:3000/get_status
```

## 7. systemd 托管

项目提供了服务文件模板：

- `deploy/qqbot-framework.service`

示例部署：

```bash
cp deploy/qqbot-framework.service /etc/systemd/system/qqbot-framework.service
systemctl daemon-reload
systemctl enable qqbot-framework
systemctl start qqbot-framework
systemctl status qqbot-framework
```

模板默认工作目录是：

```text
/opt/qqbot-framework
```

如果你实际部署路径不同，请记得改：

- `WorkingDirectory=`
- `EnvironmentFile=`
- `ExecStart=`

## 8. 启动后检查项

建议依次检查：

### 8.1 框架服务

```bash
curl http://127.0.0.1:9000/
curl http://127.0.0.1:9000/healthz
```

### 8.2 NapCat API

```bash
curl -X POST http://127.0.0.1:3000/get_status
```

### 8.3 QQ 实际消息测试

在 QQ 给机器人发送：

- `ping`
- `help`
- `签到`
- `签到状态`
- `积分`
- `群管帮助`
- `插件列表`

## 9. 数据与持久化

建议保留这些目录：

- `data/`：SQLite、插件注册表
- `napcat/config/`：NapCat 配置
- `ntqq/`：QQ 登录态
- `user_plugins/`：你安装或自己写的插件

## 10. 升级方式

### 升级框架

推荐做法：

1. 备份旧环境中的：
   - `.env`
   - `data/`
   - `user_plugins/`
   - `napcat/config/`
   - `ntqq/`
2. 替换程序文件
3. 恢复上述目录
4. 重启框架和 NapCat

### 升级插件

命令行方式：

```bash
python3 install_plugin.py upgrade 插件名
```

升级后重启机器人服务。

## 11. 迁移到新服务器

迁移时建议保留：

- `.env`
- `data/`
- `user_plugins/`
- `napcat/config/`
- `ntqq/`（如果希望尽量保留登录态）

但要注意：

- 登录态迁移后不一定总能继续有效
- 如失效，重新扫码是正常现象

## 12. 常见问题

### 12.1 `docker-compose` 老版本报 `ContainerConfig`

这是已知兼容问题。优先用：

- `docker run`

### 12.2 QQ 不回消息

依次检查：

1. `qqbot-framework` 是否健康
2. `NapCat` 是否在线
3. `ONEBOT_API_BASE` 是否正确
4. NapCat 上报地址是否正确指向 `/onebot/event`
5. 防火墙或端口占用问题

### 12.3 插件改了但没生效

当前框架默认**启动时加载插件**。因此：

- 修改插件后需要重启服务

### 12.4 群管理命令执行失败

通常是机器人在群里权限不足。

例如：

- 禁言
- 踢人
- 设管理员
- 撤回

都依赖 QQ 侧实际权限。

## 13. 安全建议

不要把以下内容打包公开分发：

- `.env`
- `data/qqbot.sqlite3`
- `ntqq/`
- `napcat/cache/`
- 登录二维码缓存

发布给别人时，请只发清理后的 release 包。

## 14. 推荐的最终使用方式

最推荐的生产组合：

- qqbot-framework：宿主机运行
- NapCat：Docker 运行
- 插件：放 `user_plugins/`
- 数据：保存在 `data/`
- systemd：托管框架进程

这是当前项目最稳定、最容易迁移的一种落地方式。
