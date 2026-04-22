# NapCat 部署说明（推荐）

这是当前项目已经验证通过的 QQ 接入方案。

## 架构

```text
QQ
  ↓ 扫码登录
NapCat
  ↓ OneBot HTTP API + HTTP 事件上报
qqbot-framework
```

## 已验证端口

- NapCat WebUI: `6099`
- NapCat OneBot HTTP API: `3000`
- qqbot-framework: `9000`

## 目录说明

```text
qqbot-framework/
├── napcat/
│   └── config/
├── ntqq/
├── deploy/
│   ├── docker-compose.napcat.yml
│   └── napcat.onebot11.template.json
└── .env
```

## 第一步：准备框架环境

```bash
cd qqbot-framework
cp .env.example .env
```

把 `.env` 改成至少这样：

```env
ONEBOT_API_BASE=http://127.0.0.1:3000
QQBOT_OWNER_IDS=你的QQ号
```

然后启动框架：

```bash
chmod +x run.sh
./run.sh
```

或使用你自己的 systemd / supervisor / docker 方式启动。

确保健康检查正常：

```bash
curl http://127.0.0.1:9000/healthz
```

预期返回：

```json
{"ok":true}
```

## 第二步：准备 NapCat 配置目录

```bash
mkdir -p napcat/config ntqq
cp deploy/napcat.onebot11.template.json napcat/config/onebot11_你的QQ号.json
```

注意：NapCat 登录后通常会按账号生成配置文件，实际生效的文件名一般类似：

```text
onebot11_123456789.json
```

如果你不知道账号文件名，可以先扫码登录一次，再进入 `napcat/config/` 看实际生成的文件名。

## 第三步：启动 NapCat

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

也可以使用：

```bash
docker-compose -f deploy/docker-compose.napcat.yml up -d
```

如果你的环境里 `docker-compose` 版本较老并出现 `ContainerConfig` 错误，优先改用上面的 `docker run`。

## 第四步：扫码登录

查看日志：

```bash
docker logs -f napcat
```

日志里会输出：

- WebUI 地址
- token
- 二维码
- 二维码解码链接

WebUI 默认类似：

```text
http://127.0.0.1:6099/webui?token=xxxxxx
```

扫码成功后，NapCat 会启动：

- OneBot HTTP API：`0.0.0.0:3000`
- HTTP 上报：`http://host.docker.internal:9000/onebot/event`

## 第五步：验证

### 1. 验证 QQ 已登录

```bash
curl -X POST http://127.0.0.1:3000/get_login_info
```

### 2. 验证 OneBot 状态

```bash
curl -X POST http://127.0.0.1:3000/get_status
```

### 3. 验证框架健康

```bash
curl http://127.0.0.1:9000/healthz
```

### 4. 在 QQ 中实际测试

给机器人发送：

- `/ping`
- `/help`
- `/签到`
- `/积分`
- `/插件列表`

## 持久化建议

请保留以下目录：

- `ntqq/`：QQ 登录态和缓存
- `napcat/config/`：NapCat 配置
- `data/`：框架 SQLite 数据

这样重启后不用重新全量配置。

## 已知问题

### 1. `docker-compose` 老版本报 `ContainerConfig`

这是旧版 docker-compose 的兼容问题。

解决办法：

- 优先使用 `docker run`
- 或升级 docker-compose

### 2. 扫码后登录态失效

NapCat 日志如果提示：

```text
快速登录错误：登录态已失效，请重新登录
```

说明需要重新扫码一次。

### 3. 端口已占用

检查：

```bash
ss -lntp | grep -E ':3000|:6099|:9000'
```

## 推荐最终配置

- qqbot-framework：宿主机运行
- NapCat：Docker 运行
- OneBot API：`127.0.0.1:3000`
- OneBot 上报：`127.0.0.1:9000/onebot/event`

这是当前项目已经实测打通的组合。
