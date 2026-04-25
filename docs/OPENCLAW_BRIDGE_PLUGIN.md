# OpenClaw Bridge 插件

把 `qqbot-framework` 接到 OpenClaw，会让机器人里的主人/管理员可以通过命令触发 OpenClaw 会话或白名单动作。

## 目标

- 只有主人或手动设置的管理员可以操作
- 普通成员无权调用
- 使用一个固定指令把后续内容原样转发给 OpenClaw
- OpenClaw 执行完成后，把返回结果再回复到 QQ
- 仍保留白名单动作扩展能力，便于后续做更强约束

## 文件位置

- 插件：`user_plugins/openclaw_bridge.py`

## 环境变量

写入 `qqbot-framework/.env`：

```env
QQBOT_OPENCLAW_BRIDGE_ENABLED=true
QQBOT_OPENCLAW_BRIDGE_BASE_URL=http://127.0.0.1:3001
QQBOT_OPENCLAW_BRIDGE_API_KEY=
QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION=agent:main:subagent:cee05ebc-ddb7-4d11-993d-1bd393ef70af
QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS=123456,234567
QQBOT_OPENCLAW_BRIDGE_COMMAND=爪爪
QQBOT_OPENCLAW_BRIDGE_ALIASES=小小
QQBOT_OPENCLAW_BRIDGE_ALLOWED_ACTIONS=xiaoxiao3d,weather,github,session_send
QQBOT_OPENCLAW_BRIDGE_ALLOW_GROUP=true
QQBOT_OPENCLAW_BRIDGE_ALLOW_PRIVATE=true
QQBOT_OPENCLAW_BRIDGE_TIMEOUT=90
QQBOT_OPENCLAW_BRIDGE_CONTINUE_PRIVATE=true
QQBOT_OPENCLAW_BRIDGE_CONTINUE_GROUP=false
QQBOT_OPENCLAW_BRIDGE_CONTINUE_WINDOW_SECONDS=600
```

## 权限规则

以下用户可以操作：

- `QQBOT_OWNER_IDS` 中的主人
- `QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS` 中的管理员

## 已实现命令

- `爪爪 你的需求`（默认固定直通指令，可用环境变量改名）
- `OpenClaw帮助`
- `OpenClaw状态`
- `设置OpenClaw管理员 QQ号`
- `删除OpenClaw管理员 QQ号`
- `OpenClaw管理员列表`
- `配置OpenClaw桥接 地址 [Key] [sessionKey]`

例如：

```text
爪爪 用 xiaoxiao3d 登录后台
爪爪 帮我查今天北京天气
爪爪 去看一下 GitHub 仓库的最新 issue
```

## 固定指令模式

默认固定指令是：

- `爪爪`
- `小小`（兼容别名）

当 QQ 消息是：

```text
爪爪 你的需求内容
```

插件会把“你的需求内容”原样转发给 OpenClaw 默认会话，然后把 OpenClaw 的回复再返回给 QQ。

如果你想改唤醒词，可修改：

```env
QQBOT_OPENCLAW_BRIDGE_COMMAND=爪爪
```

## 连续对话

当前行为：

- 私聊：支持连续对话。先用 `爪爪 ...` 或 `小小 ...` 唤醒后，后续第二段、第三段纯文本消息会继续转发给 OpenClaw。
- 群聊：当前默认只支持显式唤醒，不默认开启自动续聊，避免误接别人的消息。

可通过环境变量控制：

```env
QQBOT_OPENCLAW_BRIDGE_CONTINUE_PRIVATE=true
QQBOT_OPENCLAW_BRIDGE_CONTINUE_GROUP=false
QQBOT_OPENCLAW_BRIDGE_CONTINUE_WINDOW_SECONDS=600
```

## 动作白名单

虽然日常使用推荐固定指令直通，但代码里仍保留了白名单动作映射能力，后续你可以继续扩展 `_run_action()`，增加更严格的受控动作。

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
- sessionKey 最好固定到一个专用 OpenClaw 会话，不要复用 `agent:main:main` 这种共享主会话
- 当前联调可用的专用 bridge session：`agent:main:subagent:cee05ebc-ddb7-4d11-993d-1bd393ef70af`
- 这个专用会话的目标风格应是“正常聊天态”：直接回答用户问题，不暴露 toolCall / toolUse / memory_search / read / JSON 中间态
