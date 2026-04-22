from __future__ import annotations

import time
from pathlib import Path

from app.card_mode import build_image_url, build_text_card, get_card_mode
from app.config import settings
from app.core.plugin import CommandPlugin, PluginMeta
from app.renderers.card_image import render_info_card

CARDS_DIR = Path(settings.data_dir) / "cards"

image_card_demo = CommandPlugin(
    name="image_card_demo",
    command="测试图片卡",
    description="render and send image card demo",
    meta=PluginMeta(name="image_card_demo", version="1.1.0", author="OpenClaw", description="测试图片卡发送能力"),
)


@image_card_demo.handle
async def on_image_card_demo(ctx):
    lines = [
        "这张卡片支持全局文字/图片模式切换",
        "当前内容由机器人本地代码直接生成",
        "后续可扩展成签到卡、更新卡、菜单卡、排行榜卡",
    ]
    footer = "可发送：卡片模式 / 切换卡片模式 文字 / 切换卡片模式 图片"

    if get_card_mode() != "image":
        await ctx.reply(build_text_card("QQ机器人卡片测试", lines, footer))
        return

    ts = int(time.time())
    output = CARDS_DIR / f"demo_{ts}.png"
    path = render_info_card(
        title="QQ机器人图片卡片",
        subtitle="本地代码生成 · Pillow 渲染",
        lines=lines,
        footer=footer,
        output_path=str(output),
    )
    public = build_image_url(Path(path).name)
    await ctx.reply_image_with_text("测试图片卡如下：", public)
