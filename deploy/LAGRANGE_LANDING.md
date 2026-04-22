# Lagrange.OneBot 落地部署说明

这是一套 **qqbot-framework + Lagrange.OneBot** 的具体落地方案。

## 目标

- 支持 QQ 二维码扫码登录
- Lagrange.OneBot 负责 QQ 在线与 OneBot 接口
- qqbot-framework 负责插件、命令、积分、管理逻辑

## 架构

```text
手机 QQ 扫码
   ↓
Lagrange.OneBot
   ├─ HTTP API: http://lagrange:5700
   └─ 反向 HTTP 上报: http://qqbot-framework:9000/onebot/event
   ↓
qqbot-framework
```

## 目录建议

```text
project/
├── qqbot-framework/
├── lagrange/
│   ├── appsettings.json
│   └── data/
```

## 关键配置

### qqbot-framework .env

```env
ONEBOT_API_BASE=http://lagrange:5700
QQBOT_OWNER_IDS=你的QQ号
QQBOT_MARKET_URL=
QQBOT_DATA_DIR=./data
QQBOT_SQLITE_PATH=./data/qqbot.sqlite3
```

### Lagrange.OneBot 需要满足

- HTTP API 监听 `0.0.0.0:5700`
- 反向 HTTP POST 到 `http://qqbot-framework:9000/onebot/event`
- 开启二维码登录
- 持久化登录状态目录

## 首次登录流程

1. 启动 `docker compose up -d`
2. 查看 Lagrange 日志
3. 终端中会出现二维码或登录提示
4. 用手机 QQ 扫码确认
5. 成功后登录状态写入持久化目录
6. qqbot-framework 开始接收消息

## 重启后的行为

如果登录状态目录已持久化，通常不需要每次重新扫码。

## 风险提示

QQ 适配器生态变化快，字段和镜像标签会变动。
部署前请根据你实际采用的 Lagrange.OneBot 版本，核对其官方文档中的配置键名。

## 验证

- 打开 `http://服务器IP:9000/healthz` 应返回 `{"ok": true}`
- 给机器人发送 `/help`
- 如果有主人权限，再试 `/插件列表`
