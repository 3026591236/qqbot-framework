from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta
from app.plugin_market import get_market_plugin, list_market_plugins


def _plugins_dir() -> Path:
    base = Path(__file__).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    return base


def _download(url: str) -> bytes:
    with httpx.Client(timeout=20) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_filename(name: str) -> str:
    return "market_" + "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)


plugin = CommandPlugin(
    name="plugin_market_install",
    command="安装插件",
    description="install a plugin from market",
    meta=PluginMeta(name="plugin_market_install", version="1.0.0", author="OpenClaw", description="从插件商店安装插件"),
)


@plugin.handle
async def on_install(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以安装插件")
        return

    name = (ctx.args or "").strip()
    if not name:
        await ctx.reply("用法：安装插件 插件名\n先看：插件市场")
        return

    item = get_market_plugin(name)
    if not item:
        # also allow fuzzy try: show top few
        candidates = [p.name for p in list_market_plugins()]
        await ctx.reply("插件商店未找到该插件。\n可用：" + " / ".join(candidates[:20]))
        return

    if not (item.url or "").strip():
        await ctx.reply("该插件条目缺少下载地址（url 为空），请先在插件商店仓库补齐 market.json")
        return

    try:
        data = _download(item.url)
    except Exception as exc:
        await ctx.reply(f"下载失败：{exc}")
        return

    got = _sha256(data)
    expected = (item.sha256 or "").strip()
    if expected and expected != got:
        await ctx.reply(
            "插件校验失败，已拒绝安装。\n"
            f"期望 sha256：{expected}\n"
            f"实际 sha256：{got}"
        )
        return

    filename = _safe_filename(item.name) + ".py"
    target = _plugins_dir() / filename
    target.write_bytes(data)

    await ctx.reply(
        "安装完成（已写入 user_plugins/）\n"
        f"插件：{item.name}\n"
        f"文件：{target.name}\n"
        "提示：当前框架不支持热加载插件，需要重启服务后生效。"
    )
