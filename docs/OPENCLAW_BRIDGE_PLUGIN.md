# OpenClaw Bridge 插件

把 `qqbot-framework` 接到 OpenClaw，会让机器人里的主人/管理员可以通过命令触发 OpenClaw 会话或白名单动作。

## 目标

- 只有主人或手动设置的管理员可以操作
- 普通成员无权调用
- 默认只开放白名单动作，避免高风险指令乱跑
- 可以把固定动作路由到 OpenClaw，例如：
  - `xiaoxiao3d`
  - `weather`
  - `github`
  - 直接发送一段消息给指定 OpenClaw session

## 文件位置

- 插件：`user_plugins/openclaw_bridge.py`

## 环境变量

写入 `qqbot-framework/.env`：

```env
QQBOT_OPENCLAW_BRIDGE_ENABLED=true
QQBOT_OPENCLAW_BRIDGE_BASE_URL=http://127.0.0.1:3001
QQBOT_OPENCLAW_BRIDGE_API_KEY=
QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION=
QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS=123456,234567
QQBOT_OPENCLAW_BRIDGE_ALLOWED_ACTIONS=xiaoxiao3d,weather,github,session_send
QQBOT_OPENCLAW_BRIDGE_ALLOW_GROUP=true
QQBOT_OPENCLAW_BRIDGE_ALLOW_PRIVATE=true
QQBOT_OPENCLAW_BRIDGE_TIMEOUT=90
```

## 权限规则

以下用户可以操作：

- `QQBOT_OWNER_IDS` 中的主人
- `QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS` 中的管理员

## 已实现命令

- `OpenClaw帮助`
- `OpenClaw状态`
- `OpenClaw动作 xiaoxiao3d`
- `OpenClaw动作 weather 北京`
- `OpenClaw动作 github owner/repo`
- `OpenClaw发送 具体内容`
- `设置OpenClaw管理员 QQ号`
- `删除OpenClaw管理员 QQ号`
- `OpenClaw管理员列表`
- `配置OpenClaw桥接 地址 [Key] [sessionKey]`

## 动作白名单

当前默认白名单：

- `xiaoxiao3d`
- `weather`
- `github`
- `session_send`

你可以继续扩展 `_run_action()`，增加更多固定动作映射。

## 推荐接法

如果你本机 OpenClaw 有一个可供桥接的 HTTP 服务，建议这个插件只负责：

1. QQ 侧权限控制
2. 指令解析
3. 转发给 OpenClaw 指定 session
4. 返回结果给 QQ

## 安全建议

- 不要默认开放任意 shell / exec
- 先做白名单动作，不要做任意 prompt 透传
- 高风险动作建议拆成单独 action 名并加二次确认
- sessionKey 最好固定到一个专用 OpenClaw 会话
