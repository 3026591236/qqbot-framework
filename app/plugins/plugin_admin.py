from __future__ import annotations

from app.auth import is_owner
from app.plugin_market import list_market_plugins
from app.plugin_registry import get_plugin_info, list_plugins, set_enabled

plugin = None  # compatibility marker for loader; actual plugins below

from app.core.plugin import CommandPlugin, PluginMeta


def _human_source(info: dict) -> str:
    package = info.get("package") or ""
    if package == "app.plugins":
        return "系统内置"
    if package == "user_plugins":
        return "扩展插件"
    return package or "未知来源"


def _human_type(info: dict) -> str:
    mapping = {
        "command": "命令",
        "keyword": "关键词",
        "regex": "正则",
    }
    return mapping.get((info.get("plugin_type") or "").lower(), info.get("plugin_type") or "未知")


def _onoff(value: bool) -> str:
    return "已启用" if value else "已禁用"

plugin_list = CommandPlugin(
    name="plugin_list",
    command="/插件列表",
    description="list installed plugins",
    meta=PluginMeta(name="plugin_list", version="1.0.0", author="OpenClaw", description="list installed plugins"),
)


@plugin_list.handle
async def on_plugin_list(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("没有权限")
        return
    data = list_plugins()
    if not data:
        await ctx.reply("当前没有已登记插件")
        return

    lines = ["插件列表："]
    for name, info in sorted(data.items()):
        desc = info.get("description") or "暂无说明"
        lines.append(
            f"- {name}｜{_onoff(info.get('enabled', True))}｜{_human_source(info)}｜{_human_type(info)}"
        )
        lines.append(
            f"  说明：{desc}"
        )
        lines.append(
            f"  版本：{info.get('version', '-')}｜作者：{info.get('author', '-')}｜触发：{info.get('trigger') or '-'}"
        )
    lines.append("可发送：插件详情 插件名")
    await ctx.reply("\n".join(lines)[:4000])


plugin_detail = CommandPlugin(
    name="plugin_detail",
    command="/插件详情",
    description="show plugin detail",
    meta=PluginMeta(name="plugin_detail", version="1.1.0", author="OpenClaw", description="show plugin detail"),
)


@plugin_detail.handle
async def on_plugin_detail(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("没有权限")
        return
    text = (ctx.text or "").strip()
    for prefix in ("/插件详情", "插件详情"):
        if text == prefix:
            await ctx.reply("用法：插件详情 插件名")
            return
        if text.startswith(prefix + " "):
            name = text[len(prefix):].strip()
            break
    else:
        await ctx.reply("用法：插件详情 插件名")
        return

    info = get_plugin_info(name)
    if not info:
        await ctx.reply(f"未找到插件：{name}")
        return

    deps = info.get("dependencies") or []
    dep_text = "、".join(deps) if deps else "无"
    await ctx.reply(
        f"插件详情\n"
        f"名称：{name}\n"
        f"状态：{_onoff(info.get('enabled', True))}\n"
        f"来源：{_human_source(info)}\n"
        f"类型：{_human_type(info)}\n"
        f"说明：{info.get('description') or '暂无说明'}\n"
        f"版本：{info.get('version', '-')}\n"
        f"作者：{info.get('author', '-')}\n"
        f"触发：{info.get('trigger') or '-'}\n"
        f"模块：{info.get('module') or '-'}\n"
        f"依赖：{dep_text}"
    )


plugin_enable = CommandPlugin(
    name="plugin_enable",
    command="/启用插件",
    description="enable plugin",
    meta=PluginMeta(name="plugin_enable", version="1.0.0", author="OpenClaw", description="enable plugin"),
)


@plugin_enable.handle
async def on_plugin_enable(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("没有权限")
        return
    name = ctx.text[len("/启用插件"):].strip()
    if not name:
        await ctx.reply("用法：/启用插件 插件名")
        return
    set_enabled(name, True)
    await ctx.reply(f"已启用插件：{name}")


plugin_disable = CommandPlugin(
    name="plugin_disable",
    command="/禁用插件",
    description="disable plugin",
    meta=PluginMeta(name="plugin_disable", version="1.0.0", author="OpenClaw", description="disable plugin"),
)


@plugin_disable.handle
async def on_plugin_disable(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("没有权限")
        return
    name = ctx.text[len("/禁用插件"):].strip()
    if not name:
        await ctx.reply("用法：/禁用插件 插件名")
        return
    set_enabled(name, False)
    await ctx.reply(f"已禁用插件：{name}")


plugin_market = CommandPlugin(
    name="plugin_market",
    command="/插件市场",
    description="list market plugins",
    meta=PluginMeta(name="plugin_market", version="1.0.0", author="OpenClaw", description="list market plugins"),
)


@plugin_market.handle
async def on_plugin_market(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("没有权限")
        return
    items = list_market_plugins()
    if not items:
        await ctx.reply("插件市场为空")
        return
    lines = [f"{item.name} | {item.version} | {item.description}" for item in items]
    await ctx.reply("插件市场：\n" + "\n".join(lines))
