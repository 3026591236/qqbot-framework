# 插件编写规范

本文档用于说明 `qqbot-framework` 的插件结构、加载方式、上下文对象、最佳实践与注意事项。

## 1. 插件放在哪里

框架会自动扫描两个插件包：

- `app/plugins/`：内置插件
- `user_plugins/`：用户插件 / 第三方插件

推荐：

- 官方内置功能放 `app/plugins/`
- 你自己写的业务插件、群管插件、第三方扩展放 `user_plugins/`

## 2. 插件会如何被加载

启动时会自动执行插件发现：

- `app.main` 启动时调用 `discover_all_plugins()`
- `app.plugin_loader` 会扫描 `app.plugins` 和 `user_plugins`
- 只要模块里存在：
  - `plugin` 变量
  - 或任意拥有 `dispatch` 和 `name` 属性的对象
  就会被当成插件加载

这意味着：

- 一个文件可以只导出一个 `plugin`
- 也可以在一个文件里放多个插件对象
- 像 `group_admin.py` 这种“大插件包”完全没问题

## 3. 支持的插件类型

当前框架内置三种基础插件：

### 3.1 命令插件 `CommandPlugin`

适合：

- `ping`
- `签到`
- `群管帮助`
- `插件列表`

示例：

```python
from app.core.plugin import CommandPlugin, PluginMeta

plugin = CommandPlugin(
    name="hello",
    command="hello",
    description="say hello",
    meta=PluginMeta(name="hello", version="1.0.0", author="you", description="hello plugin"),
)

@plugin.handle
async def on_hello(ctx):
    await ctx.reply("你好，我在。")
```

说明：

- 命令支持带 `/` 和不带 `/` 两种写法
- 例如命令写 `ping`，用户发 `ping` 或 `/ping` 都能匹配

---

### 3.2 关键词插件 `KeywordPlugin`

适合：

- 包含某个关键词就响应
- 轻量问候类插件

示例：

```python
from app.core.plugin import KeywordPlugin, PluginMeta

plugin = KeywordPlugin(
    name="hello_keyword",
    keyword="你好",
    description="reply hello",
    meta=PluginMeta(name="hello_keyword", version="1.0.0", author="you", description="keyword hello"),
)

@plugin.handle
async def on_keyword(ctx):
    await ctx.reply("你好呀")
```

---

### 3.3 正则插件 `RegexPlugin`

适合：

- 匹配数字、订单号、特定格式文本
- 复杂消息规则

示例：

```python
from app.core.plugin import RegexPlugin, PluginMeta

plugin = RegexPlugin(
    name="number_echo",
    pattern=r"^查单\s+\d+$",
    description="match order query",
    meta=PluginMeta(name="number_echo", version="1.0.0", author="you", description="regex example"),
)

@plugin.handle
async def on_regex(ctx):
    await ctx.reply(f"收到：{ctx.text}")
```

## 4. MessageContext 可用字段

插件 handler 会收到 `ctx`，当前可用能力包括：

### 基础字段

- `ctx.text`：文本内容
- `ctx.user_id`：发送者 QQ
- `ctx.group_id`：群号，私聊时为 `None`
- `ctx.message_type`：`group` 或 `private`
- `ctx.raw_event`：完整 OneBot 原始事件

### 便捷属性

- `ctx.args`：命令后的参数文本
- `ctx.message_id`：消息 ID
- `ctx.sender`：发送者原始信息字典
- `ctx.role`：群角色，常见为 `member/admin/owner`
- `ctx.is_group`：是否群聊

### 回复能力

- `await ctx.reply("文本")`

当前 `reply()` 会自动判断：

- 群消息 → `send_group_msg`
- 私聊消息 → `send_private_msg`

## 5. OneBot API 能力

当前已经封装的接口位于：`app/adapters/onebot.py`

已支持：

- `send_private_msg(user_id, message)`
- `send_group_msg(group_id, message)`
- `delete_msg(message_id)`
- `set_group_ban(group_id, user_id, duration)`
- `set_group_whole_ban(group_id, enable)`
- `set_group_kick(group_id, user_id, reject_add_request=False)`
- `set_group_admin(group_id, user_id, enable)`
- `set_group_card(group_id, user_id, card)`
- `set_group_name(group_id, group_name)`
- `get_group_member_info(group_id, user_id, no_cache=False)`
- `get_group_member_list(group_id)`

插件中可以直接使用：

```python
await ctx.api.set_group_ban(ctx.group_id, 123456, 600)
```

## 6. 插件元信息规范

建议每个插件都写完整 `PluginMeta`：

```python
PluginMeta(
    name="plugin_name",
    version="1.0.0",
    author="your_name",
    description="what this plugin does",
    dependencies=[],
)
```

字段建议：

- `name`：唯一名称，尽量稳定，不要频繁改
- `version`：建议语义化版本，如 `1.0.0`
- `author`：作者名
- `description`：简短描述
- `dependencies`：Python 依赖包名列表

## 7. 插件命名建议

推荐：

- 文件名：小写下划线，如 `group_admin.py`
- 插件名：小写下划线，如 `group_admin_help`
- 命令名：面向最终用户，可中文，如 `群管帮助`

不要：

- 文件名和插件名混乱无规则
- 一个文件里放大量匿名对象却没有清晰命名

## 8. 状态持久化建议

如果插件需要存储数据，推荐：

- 使用 `app.db.get_conn()`
- 存到 SQLite
- 在 `app.db.init_db()` 中补充建表逻辑

示例：

```python
from app.db import get_conn

with get_conn() as conn:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS my_plugin_data (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )
```

如果你的插件依赖固定表结构，推荐：

- 把建表逻辑放在 `init_db()` 中
- 或在插件模块导入时调用 `_ensure_tables()`

当前项目中：

- 积分/签到数据在 `user_points`
- 群管 v2 数据在 `group_admin_settings` / `group_admin_words` / `group_admin_whitelist` / `group_admin_warns`

## 9. 权限控制建议

群管理类插件一定要做权限判断。

推荐检查：

- `ctx.is_group`
- `ctx.role`
- `is_owner(ctx.user_id)`

示例：

```python
from app.auth import is_owner

if not ctx.is_group:
    await ctx.reply("这个命令只能在群里用")
    return

if ctx.role not in {"admin", "owner"} and not is_owner(ctx.user_id):
    await ctx.reply("你没有权限")
    return
```

## 10. 错误处理建议

建议：

- 对外部 API 调用加异常保护
- 对权限不足、参数错误给出明确提示
- 不要把 Python traceback 直接发给 QQ 用户

示例：

```python
try:
    await ctx.api.delete_msg(ctx.message_id)
except Exception:
    await ctx.reply("撤回失败，请检查机器人权限")
```

## 11. 最佳实践

### 推荐

- 一个插件只做一类事
- 命令文案清晰
- 参数错误时返回示例用法
- 对群聊和私聊逻辑分开处理
- 把业务逻辑写进 `app/services.py` 或独立 service 文件，插件层负责交互

### 不推荐

- 在插件里堆大量 SQL 和复杂业务
- 直接依赖未封装的临时字段
- 启动时执行高风险操作
- 把账号密码、token 写死在插件里

## 12. 示例：一个最小可用插件

文件：`user_plugins/hello_demo.py`

```python
from app.core.plugin import CommandPlugin, PluginMeta

plugin = CommandPlugin(
    name="hello_demo",
    command="hello",
    description="demo plugin",
    meta=PluginMeta(name="hello_demo", version="1.0.0", author="demo", description="hello demo"),
)

@plugin.handle
async def on_hello(ctx):
    who = ctx.user_id or "unknown"
    await ctx.reply(f"hello, {who}")
```

重启框架后即可使用：

- `hello`
- `/hello`

## 13. 插件安装与管理

命令行工具：`install_plugin.py`

```bash
python3 install_plugin.py install /path/to/plugin.py
python3 install_plugin.py install market:plugin_name
python3 install_plugin.py upgrade plugin_name
python3 install_plugin.py uninstall plugin_name
python3 install_plugin.py enable plugin_name
python3 install_plugin.py disable plugin_name
python3 install_plugin.py list
python3 install_plugin.py market
```

聊天内主人命令也支持基础管理：

- `插件列表`
- `启用插件 名称`
- `禁用插件 名称`
- `插件市场`

## 14. 当前限制

目前框架稳定支持：

- 文本收发
- 群管理 API
- 命令/关键词/正则插件

目前还未统一封装：

- JSON 卡片消息
- XML 卡片消息
- 图片/语音/文件等完整消息段构造器
- notice/request 事件的完整高级封装

如果需要这些能力，建议扩展 `app/adapters/onebot.py` 与 `MessageContext.reply()`。

## 15. 发布插件建议

如果你要把插件分享给别人：

- 尽量只依赖框架公开接口
- 写清楚需要的环境变量
- 写清楚需要的数据库表
- 写清楚权限要求
- 提供 README 或示例命令

---

这份文档描述的是当前仓库实际能力，而不是理想化未来设计。写插件时请以实际代码接口为准。
