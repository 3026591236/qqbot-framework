# OpenClaw Bridge Server

这是给 `qqbot-framework` 的 `openclaw_bridge.py` 插件配套的小型 HTTP bridge 服务。

作用：

1. QQ 机器人插件调用本地 bridge
2. bridge 再把消息转发给 OpenClaw 的 session 接口
3. 把 OpenClaw 返回结果再回给 QQ 插件

## 文件

- 服务入口：`app/openclaw_bridge_server.py`
- 启动脚本：`scripts/run_openclaw_bridge.sh`

## 环境变量

```env
OPENCLAW_BASE_URL=http://127.0.0.1:xxxx
OPENCLAW_API_KEY=
OPENCLAW_BRIDGE_TOKEN=your-secret-token
OPENCLAW_TIMEOUT=120
QQBOT_OPENCLAW_BRIDGE_HOST=0.0.0.0
QQBOT_OPENCLAW_BRIDGE_PORT=3001
```

说明：

- `OPENCLAW_BASE_URL`：真正的 OpenClaw HTTP 服务地址
- `OPENCLAW_API_KEY`：如果 OpenClaw HTTP 服务需要 Bearer 鉴权，就填这个
- `OPENCLAW_BRIDGE_TOKEN`：给 QQ 插件调用本 bridge 时用的 token

## 启动

```bash
cd /root/.openclaw/workspace/qqbot-framework
bash scripts/run_openclaw_bridge.sh
```

## 健康检查

```bash
curl http://127.0.0.1:3001/health
```

## 插件侧配置示例

写入 `qqbot-framework/.env`：

```env
QQBOT_OPENCLAW_BRIDGE_ENABLED=true
QQBOT_OPENCLAW_BRIDGE_BASE_URL=http://127.0.0.1:3001
QQBOT_OPENCLAW_BRIDGE_API_KEY=your-secret-token
QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION=agent:main:subagent:cee05ebc-ddb7-4d11-993d-1bd393ef70af
QQBOT_OPENCLAW_BRIDGE_COMMAND=爪爪
QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS=123456,234567
```

注意：

- 这里 `QQBOT_OPENCLAW_BRIDGE_API_KEY` 对应的是 bridge 服务的 `OPENCLAW_BRIDGE_TOKEN`
- 如果你不想开放无鉴权访问，务必设置 token
- 默认目标 session 建议使用专用 bridge 会话，不要复用 `agent:main:main`
- bridge 应只把最终文本回复返回给 QQ，不应透传 toolCall/toolUse/JSON 中间态
- 当前插件侧已支持私聊连续对话接管；群聊自动续聊默认关闭，避免误接他人消息
