from __future__ import annotations

from app.auth import is_owner
from app.card_mode import get_card_mode, get_card_mode_label, set_card_mode, set_group_card_mode
from app.core.plugin import CommandPlugin, PluginMeta

card_mode_status = CommandPlugin(
    name="card_mode_status",
    command="卡片模式",
    description="show global card mode",
    meta=PluginMeta(name="card_mode_status", version="1.0.0", author="OpenClaw", description="查看全局卡片模式"),
)


@card_mode_status.handle
async def on_card_mode_status(ctx):
    if ctx.is_group and ctx.group_id is not None:
        await ctx.reply(
            "当前卡片模式\n"
            f"本群模式：{get_card_mode_label(ctx.group_id)}\n"
            f"全局默认：{get_card_mode_label()}\n"
            "可发送：本群切换卡片模式 文字\n"
            "或发送：本群切换卡片模式 图片"
        )
        return
    await ctx.reply(
        "当前全局卡片模式\n"
        f"模式：{get_card_mode_label()}\n"
        "说明：私聊和未单独设置的群会使用全局模式\n"
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
        "未单独设置的群和私聊将使用这个模式。"
    )


group_switch_card_mode = CommandPlugin(
    name="group_switch_card_mode",
    command="本群切换卡片模式",
    description="switch current group card mode",
    meta=PluginMeta(name="group_switch_card_mode", version="1.0.0", author="OpenClaw", description="切换本群卡片模式"),
)


@group_switch_card_mode.handle
async def on_group_switch_card_mode(ctx):
    if not ctx.is_group or ctx.group_id is None:
        await ctx.reply("这个命令只能在群里用")
        return
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以切换本群卡片模式")
        return
    value = ctx.args.strip()
    if not value:
        await ctx.reply("用法：本群切换卡片模式 文字\n或：本群切换卡片模式 图片")
        return
    try:
        mode = set_group_card_mode(ctx.group_id, value)
    except Exception as exc:
        await ctx.reply(f"切换失败：{exc}")
        return
    label = "图片卡片" if mode == "image" else "文字卡片"
    await ctx.reply(f"已切换本群卡片模式：{label}")
