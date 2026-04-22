from __future__ import annotations

import os

from app.auth import is_owner
from app.card_mode import _save_env_value, get_card_style_label, list_card_style_choices, normalize_card_style
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
    current_key = normalize_card_style(os.getenv(STYLE_KEY, "light"))
    await ctx.reply(
        "图片卡片风格（机器人渲染图片卡片专用）\n"
        f"当前：{get_card_style_label(current_key)}\n"
        f"可选：{list_card_style_choices()}\n"
        "用法：切换卡片风格 <风格名>\n"
        "示例：切换卡片风格 黑金\n"
        "（支持中文别名）"
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

    style = normalize_card_style(ctx.args)
    if not style:
        await ctx.reply(
            "用法：切换卡片风格 <风格名>\n"
            f"可选：{list_card_style_choices()}\n"
            "示例：切换卡片风格 紧凑"
        )
        return

    # validate
    from app.renderers.card_image import CARD_STYLES

    if style not in set(CARD_STYLES.keys()):
        await ctx.reply(
            "不支持的风格。\n"
            f"可选：{list_card_style_choices()}\n"
            "示例：切换卡片风格 樱粉"
        )
        return

    os.environ[STYLE_KEY] = style
    _save_env_value(STYLE_KEY, style)
    await ctx.reply(f"已切换图片卡片风格：{style}")
