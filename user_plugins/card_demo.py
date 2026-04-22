from __future__ import annotations

import html
import json

from app.core.plugin import CommandPlugin, PluginMeta

plugin = None

card_help = CommandPlugin(
    name="card_help",
    command="卡片帮助",
    description="show card help",
    meta=PluginMeta(name="card_help", version="1.0.0", author="OpenClaw", description="show card help"),
)


def _build_fallback_card(title: str, desc: str, url: str) -> str:
    title = html.escape(title.strip())
    desc = html.escape(desc.strip())
    url = url.strip()
    return (
        "┏━━━〔 卡片消息 〕━━━\n"
        f"┃ 标题：{title}\n"
        f"┃ 内容：{desc}\n"
        f"┃ 链接：{url}\n"
        "┗━━━━━━━━━━━━"
    )


@card_help.handle
async def on_card_help(ctx):
    await ctx.reply(
        "卡片命令：\n"
        "测试卡片json\n"
        "测试卡片xml\n"
        "测试伪卡片\n"
        "发json卡片 标题|内容|链接\n"
        "发xml卡片 标题|内容|链接\n"
        "发伪卡片 标题|内容|链接"
    )


send_test_json_card = CommandPlugin(
    name="send_test_json_card",
    command="测试卡片json",
    description="send test json card",
    meta=PluginMeta(name="send_test_json_card", version="1.0.0", author="OpenClaw", description="send test json card"),
)


@send_test_json_card.handle
async def on_send_test_json_card(ctx):
    payload = {
        "app": "com.tencent.structmsg",
        "desc": "新闻",
        "view": "news",
        "ver": "0.0.0.1",
        "prompt": "[QQ机器人卡片]",
        "meta": {
            "news": {
                "title": "QQ机器人卡片测试",
                "desc": "这是一张通过 OneBot JSON 段发送的测试卡片",
                "jumpUrl": "https://docs.openclaw.ai",
            }
        },
        "config": {"autosize": True},
    }
    await ctx.reply_json_card(json.dumps(payload, ensure_ascii=False))


send_test_xml_card = CommandPlugin(
    name="send_test_xml_card",
    command="测试卡片xml",
    description="send test xml card",
    meta=PluginMeta(name="send_test_xml_card", version="1.0.0", author="OpenClaw", description="send test xml card"),
)


@send_test_xml_card.handle
async def on_send_test_xml_card(ctx):
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<msg serviceID="1" templateID="1" action="web" brief="[QQ机器人卡片]">'
        '<item layout="2">'
        '<title>QQ机器人 XML 卡片测试</title>'
        '<summary>这是一张通过 OneBot XML 段发送的测试卡片</summary>'
        '</item>'
        '<source name="qqbot-framework" icon="" url="https://docs.openclaw.ai"/>'
        '</msg>'
    )
    await ctx.reply_xml_card(xml)


def _parse_fields(raw: str) -> tuple[str, str, str] | None:
    raw = raw.strip()
    if not raw:
        return None
    parts = [x.strip() for x in raw.split("|", 2)]
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


send_custom_json_card = CommandPlugin(
    name="send_custom_json_card",
    command="发json卡片",
    description="send custom json card",
    meta=PluginMeta(name="send_custom_json_card", version="1.0.0", author="OpenClaw", description="send custom json card"),
)


@send_custom_json_card.handle
async def on_send_custom_json_card(ctx):
    fields = _parse_fields(ctx.args)
    if not fields:
        await ctx.reply("用法：发json卡片 标题|内容|链接")
        return
    title, desc, url = fields
    payload = {
        "app": "com.tencent.structmsg",
        "desc": "新闻",
        "view": "news",
        "ver": "0.0.0.1",
        "prompt": f"[卡片] {title}",
        "meta": {"news": {"title": title, "desc": desc, "jumpUrl": url}},
        "config": {"autosize": True},
    }
    try:
        await ctx.reply_json_card(json.dumps(payload, ensure_ascii=False))
    except Exception:
        await ctx.reply(_build_fallback_card(title, desc, url))


send_custom_xml_card = CommandPlugin(
    name="send_custom_xml_card",
    command="发xml卡片",
    description="send custom xml card",
    meta=PluginMeta(name="send_custom_xml_card", version="1.0.0", author="OpenClaw", description="send custom xml card"),
)


@send_custom_xml_card.handle
async def on_send_custom_xml_card(ctx):
    fields = _parse_fields(ctx.args)
    if not fields:
        await ctx.reply("用法：发xml卡片 标题|内容|链接")
        return
    title, desc, url = fields
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<msg serviceID="1" templateID="1" action="web" brief="[卡片] {title}">'
        '<item layout="2">'
        f'<title>{title}</title>'
        f'<summary>{desc}</summary>'
        '</item>'
        f'<source name="qqbot-framework" icon="" url="{url}"/>'
        '</msg>'
    )
    try:
        await ctx.reply_xml_card(xml)
    except Exception:
        await ctx.reply(_build_fallback_card(title, desc, url))


send_fallback_card = CommandPlugin(
    name="send_fallback_card",
    command="发伪卡片",
    description="send fallback card",
    meta=PluginMeta(name="send_fallback_card", version="1.0.0", author="OpenClaw", description="send fallback card"),
)


@send_fallback_card.handle
async def on_send_fallback_card(ctx):
    fields = _parse_fields(ctx.args)
    if not fields:
        await ctx.reply("用法：发伪卡片 标题|内容|链接")
        return
    title, desc, url = fields
    await ctx.reply(_build_fallback_card(title, desc, url))


send_test_fallback_card = CommandPlugin(
    name="send_test_fallback_card",
    command="测试伪卡片",
    description="send fallback test card",
    meta=PluginMeta(name="send_test_fallback_card", version="1.0.0", author="OpenClaw", description="send fallback test card"),
)


@send_test_fallback_card.handle
async def on_send_test_fallback_card(ctx):
    await ctx.reply(_build_fallback_card("QQ机器人伪卡片测试", "这是一种稳定替代官方卡片的文本卡片方案", "https://docs.openclaw.ai"))
