from __future__ import annotations

from app.auth import is_owner
from app.card_mode import get_card_mode, get_card_mode_label, set_card_mode
from app.core.plugin import CommandPlugin, PluginMeta

card_mode_status = CommandPlugin(
    name="card_mode_status",
    command="卡片模式",
    description="show global card mode",
    meta=PluginMeta(name="card_mode_status", version="1.0.0", author="OpenClaw", description="查看全局卡片模式"),
)


@card_mode_status.handle
async def on_card_mode_status(ctx):
    await ctx.reply(
        "当前全局卡片模式\n"
        f"模式：{get_card_mode_label()}\n"
        "说明：当切换为图片卡片模式时，机器人后续大部分文字回复会自动转成图片卡片\n"
        "可发送：切换卡片模式 文字\n"
        "或发送：切换卡片模式 图片"
    )


switch_card_mode = CommandPlugin(
    name="switch_card_mode",
    command="切换卡片模式",
    description="switch global card mode",
    meta=PluginMeta(name="switch_card_mode", version="1.0.0", author="OpenClaw", description="切换全局卡片模式"),
)


@switch_card_mode.handle
async def on_switch_card_mode(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以切换全局卡片模式")
        return
    value = ctx.args.strip()
    if not value:
        await ctx.reply("用法：切换卡片模式 文字\n或：切换卡片模式 图片")
        return
    try:
        mode = set_card_mode(value)
    except Exception as exc:
        await ctx.reply(f"切换失败：{exc}")
        return
    label = "图片卡片" if mode == "image" else "文字卡片"
    await ctx.reply(
        f"已切换全局卡片模式：{label}\n"
        "切换为图片卡片模式后，机器人后续大部分文字回复会自动转成图片卡片。"
    )
