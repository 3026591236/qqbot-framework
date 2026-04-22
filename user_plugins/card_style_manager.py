from __future__ import annotations

import os

from app.auth import is_owner
from app.card_mode import _save_env_value
from app.core.plugin import CommandPlugin, PluginMeta

STYLE_KEY = "QQBOT_CARD_STYLE"


plugin = CommandPlugin(
    name="card_style",
    command="卡片风格",
    description="show/set image card style",
    meta=PluginMeta(name="card_style", version="1.0.0", author="OpenClaw", description="图片卡片风格管理"),
)


@plugin.handle
async def on_card_style(ctx):
    current = os.getenv(STYLE_KEY, "light").strip().lower() or "light"
    await ctx.reply(
        "当前图片卡片风格\n"
        f"风格：{current}\n"
        "可用：light / dark / compact / minimal\n"
        "设置：切换卡片风格 light\n"
        "（仅影响机器人生成的图片卡片）"
    )


switch = CommandPlugin(
    name="switch_card_style",
    command="切换卡片风格",
    description="switch image card style",
    meta=PluginMeta(name="switch_card_style", version="1.0.0", author="OpenClaw", description="切换图片卡片风格"),
)


@switch.handle
async def on_switch(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以切换图片卡片风格")
        return

    style = (ctx.args or "").strip().lower()
    if not style:
        await ctx.reply("用法：切换卡片风格 light\n可选：light/dark/compact/minimal")
        return

    if style not in {"light", "dark", "compact", "minimal"}:
        await ctx.reply("不支持的风格。可选：light/dark/compact/minimal")
        return

    os.environ[STYLE_KEY] = style
    _save_env_value(STYLE_KEY, style)
    await ctx.reply(f"已切换图片卡片风格：{style}")
