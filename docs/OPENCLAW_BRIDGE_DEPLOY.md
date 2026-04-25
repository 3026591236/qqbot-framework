# OpenClaw Bridge 安装 / 修改 / 检查

这份文档用于把 `qqbot-framework` 接到本机 OpenClaw，并说明当前这套桥接的安装步骤、关键修改点、以及上线后如何检查是否正常。

## 一、组件说明

当前桥接由两部分组成：

1. **QQBot 插件**：`user_plugins/openclaw_bridge.py`
   - 负责权限控制
   - 负责唤醒词匹配
   - 负责把请求发给本地 bridge
   - 负责连续对话接管（当前默认仅私聊）

2. **本地 Bridge 服务**：`app/openclaw_bridge_server.py`
   - 负责连接 OpenClaw gateway websocket RPC
   - 负责设备身份认证
   - 负责向目标 session 发送消息
   - 负责只提取最终文本回复，不透传 toolCall / toolUse / JSON 中间态

---

## 二、安装步骤

### 1. 安装项目依赖

```bash
cd /root/.openclaw/workspace/qqbot-framework
source .venv/bin/activate
pip install -r requirements.txt
pip install cryptography
```

如果缺少 `uvicorn`、`httpx`、`Pillow`、`cryptography` 等依赖，先补齐再启动。

### 2. 配置 QQBot `.env`

编辑：`/root/.openclaw/workspace/qqbot-framework/.env`

至少需要这些配置：

```env
QQBOT_OPENCLAW_BRIDGE_ENABLED=true
QQBOT_OPENCLAW_BRIDGE_BASE_URL=http://127.0.0.1:3001
QQBOT_OPENCLAW_BRIDGE_API_KEY=qqbot-openclaw-bridge-local
QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION=agent:main:subagent:cee05ebc-ddb7-4d11-993d-1bd393ef70af
QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS=3026591236
QQBOT_OPENCLAW_BRIDGE_COMMAND=爪爪
QQBOT_OPENCLAW_BRIDGE_ALIASES=小小
QQBOT_OPENCLAW_BRIDGE_ALLOW_GROUP=true
QQBOT_OPENCLAW_BRIDGE_ALLOW_PRIVATE=true
QQBOT_OPENCLAW_BRIDGE_TIMEOUT=90
QQBOT_OPENCLAW_BRIDGE_CONTINUE_PRIVATE=true
QQBOT_OPENCLAW_BRIDGE_CONTINUE_GROUP=false
QQBOT_OPENCLAW_BRIDGE_CONTINUE_WINDOW_SECONDS=600
```

说明：

- `QQBOT_OPENCLAW_BRIDGE_COMMAND=爪爪`：主唤醒词
- `QQBOT_OPENCLAW_BRIDGE_ALIASES=小小`：兼容唤醒词
- `QQBOT_OPENCLAW_BRIDGE_CONTINUE_PRIVATE=true`：私聊允许连续对话
- `QQBOT_OPENCLAW_BRIDGE_CONTINUE_GROUP=false`：当前默认关闭群聊自动续聊，避免误接他人消息

### 3. 配置 bridge → OpenClaw gateway

同样在 `.env` 中补齐：

```env
OPENCLAW_GATEWAY_WS_URL=ws://127.0.0.1:18789
OPENCLAW_BRIDGE_TOKEN=qqbot-openclaw-bridge-local
```

如果 bridge 需要复用本机 OpenClaw 设备身份，确保这些文件存在：

- `/root/.openclaw/identity/device.json`
- `/root/.openclaw/identity/device-auth.json`

### 4. 启动 bridge 服务

```bash
cd /root/.openclaw/workspace/qqbot-framework
bash scripts/start_openclaw_bridge_nohup.sh
```

或者：

```bash
bash scripts/run_openclaw_bridge.sh
```

### 5. 启动 / 重启 QQBot 主服务

```bash
cd /root/.openclaw/workspace/qqbot-framework
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9000 > logs/uvicorn.log 2>&1 < /dev/null &
```

如果有旧进程，先停掉旧进程再起。

---

## 三、当前功能说明

### 1. 权限控制

只有这些人可用：

- `QQBOT_OWNER_IDS` 中的主人
- `QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS` 中的管理员

可用命令：

```text
设置OpenClaw管理员 QQ号
删除OpenClaw管理员 QQ号
OpenClaw管理员列表
```

### 2. 唤醒词

当前支持：

- `爪爪 ...`
- `小小 ...`

### 3. 私聊连续对话

当前已支持：

1. 先发送：

```text
小小 第一段内容
```

2. 后续继续发：

```text
第二段内容
第三段内容
```

在连续对话窗口内，这些后续纯文本会继续转发给 OpenClaw。

### 4. 群聊规则

当前版本：

- 群里可以用 `爪爪 ...` / `小小 ...` 触发
- **默认不启用群聊自动续聊**
- 原因：之前群聊自动续聊会误接别人的消息、图片、表情

---

## 四、当前关键修改点

### 插件侧：`user_plugins/openclaw_bridge.py`

主要改动：

1. **固定指令直通 OpenClaw**
   - 主唤醒词：`爪爪`
   - 兼容别名：`小小`

2. **兼容私聊与群聊触发**
   - 支持 `爪爪 ...`
   - 支持 `小小 ...`
   - 支持群里前置 `@机器人` / CQ at 片段

3. **连续对话接管**
   - 当前默认只对私聊开启
   - 后续第二段、第三段可继续回复

4. **非纯文本过滤**
   - 过滤 CQ 图片/表情等非纯文本消息

5. **管理员控制命令**
   - 支持添加/删除/查看 OpenClaw 管理员

### Bridge 侧：`app/openclaw_bridge_server.py`

主要改动：

1. 使用 websocket RPC 接 OpenClaw gateway，而不是假设 HTTP `/api/sessions/send`
2. 显式携带 websocket Origin，避免 `origin not allowed`
3. 复用本机设备身份，走 challenge/nonce 两阶段认证
4. `chat.final` 后再结合 `chat.history` / `session.message` 提取最终文本
5. 只把最终文本返回给 QQ，不透传 toolCall / toolUse / JSON 中间态
6. 增加 baseline_seq，避免把旧回复误当成本轮结果

---

## 五、检查步骤

### 1. 检查 bridge 健康

```bash
curl http://127.0.0.1:3001/health
```

正常应返回类似：

```json
{"ok":true,"gatewayWsUrl":"ws://127.0.0.1:18789"}
```

### 2. 检查 QQBot 是否加载插件

看日志：

```bash
tail -n 100 logs/uvicorn.log
```

确认已加载：

- `openclaw_bridge_help`
- `openclaw_bridge_status`
- `openclaw_bridge_direct`
- `openclaw_bridge_continue`

### 3. 检查私聊唤醒是否命中

私聊发送：

```text
小小 你好
```

日志里应看到：

- `plugin=openclaw_bridge_direct`
- `POST http://127.0.0.1:3001/api/sessions/send "HTTP/1.1 200 OK"`
- `POST http://127.0.0.1:3000/send_private_msg "HTTP/1.1 200 OK"`

### 4. 检查私聊连续对话是否命中

先发：

```text
小小 我现在开始说第一段
```

再发：

```text
这是第二段
这是第三段
```

日志里应看到：

- `continuation_touch key='private:...'`
- `continuation_hit key='private:...'`
- `plugin=openclaw_bridge_continue`

### 5. 检查群聊触发

群里发送：

```text
小小 帮我回复一句群里通了
```

如果群聊允许触发，日志应看到：

- `plugin=openclaw_bridge_direct`
- `message_type=group`
- `send_group_msg "HTTP/1.1 200 OK"`

### 6. 检查群聊未开启自动续聊

当前默认 `QQBOT_OPENCLAW_BRIDGE_CONTINUE_GROUP=false`。

所以群里发完一条唤醒后，后续普通消息**不应**继续命中 `openclaw_bridge_continue`。

如果仍命中，说明逻辑未收紧成功，需要继续排查。

---

## 六、常见问题

### 1. 私聊后续消息没继续回复

先查：

```bash
grep -nE 'continuation_(touch|hit|inactive|skip_non_text)' logs/uvicorn.log | tail -n 50
```

### 2. 群里误接别人消息

检查 `.env`：

```env
QQBOT_OPENCLAW_BRIDGE_CONTINUE_GROUP=false
```

并重启 QQBot。

### 3. OpenClaw 返回 toolCall / JSON 中间态

检查 bridge 是否为当前版本，确认 bridge 收口逻辑只提取最终文本。

### 4. 唤醒词不生效

确认是否与别的插件冲突；当前推荐：

- 主词：`爪爪`
- 别名：`小小`

如果冲突严重，可换新的别名。

---

## 七、建议

当前最稳的上线方式：

- **私聊**：启用连续对话
- **群聊**：只保留显式唤醒，不启用自动续聊
- **默认 session**：固定到专用 bridge session，不要复用共享主会话
- **回复风格**：只返回最终自然语言文本，不暴露内部工具链路
