from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta
from app.plugin_market import get_market_plugin, list_market_plugins


def _data_dir() -> Path:
    base = Path(__file__).resolve().parent.parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _installed_path() -> Path:
    return _data_dir() / "market_installed.json"


def _load_installed() -> dict:
    path = _installed_path()
    if not path.exists():
        return {"installed": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"installed": {}}


def _save_installed(data: dict) -> None:
    path = _installed_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _plugins_dir() -> Path:
    base = Path(__file__).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    return base


def _download(url: str) -> bytes:
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def _safe_filename(name: str) -> str:
    return "market_" + "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)


# ---- Commands ----

market_cmd = CommandPlugin(
    name="plugin_market_list",
    command="插件市场",
    description="list plugins from market",
    meta=PluginMeta(name="plugin_market_list", version="1.0.0", author="OpenClaw", description="查看插件商店"),
)


@market_cmd.handle
async def on_market(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以查看插件市场")
        return

    items = list_market_plugins()
    if not items:
        await ctx.reply("插件商店为空：请配置 QQBOT_MARKET_URL 指向 market.json")
        return

    lines = ["插件商店："]
    for p in items[:50]:
        desc = (p.description or "").strip()
        if len(desc) > 28:
            desc = desc[:28] + "…"
        lines.append(f"- {p.name} v{p.version}（{p.author}） {desc}")
    lines.append("\n用法：安装插件 插件名 / 更新插件 插件名 / 卸载插件 插件名 / 已装插件")
    await ctx.reply("\n".join(lines))


installed_cmd = CommandPlugin(
    name="plugin_market_installed",
    command="已装插件",
    description="list installed market plugins",
    meta=PluginMeta(name="plugin_market_installed", version="1.0.0", author="OpenClaw", description="查看已安装的商店插件"),
)


@installed_cmd.handle
async def on_installed(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以查看已装插件")
        return

    data = _load_installed().get("installed", {})
    if not data:
        await ctx.reply("暂无已安装的商店插件")
        return

    lines = ["已安装（来自插件商店）："]
    for name, info in sorted(data.items()):
        lines.append(f"- {name} v{info.get('version','?')} 文件={info.get('file','?')}")
    lines.append("\n用法：更新插件 插件名 / 卸载插件 插件名")
    await ctx.reply("\n".join(lines))


update_cmd = CommandPlugin(
    name="plugin_market_update",
    command="更新插件",
    description="update a plugin from market",
    meta=PluginMeta(name="plugin_market_update", version="1.0.0", author="OpenClaw", description="从插件商店更新插件"),
)


@update_cmd.handle
async def on_update(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以更新插件")
        return

    name = (ctx.args or "").strip()
    if not name:
        await ctx.reply("用法：更新插件 插件名")
        return

    installed = _load_installed()
    old = (installed.get("installed", {}) or {}).get(name)

    item = get_market_plugin(name)
    if not item:
        await ctx.reply("插件商店未找到该插件。先看：插件市场")
        return

    if not (item.url or "").strip():
        await ctx.reply("该插件条目缺少下载地址（url 为空），请先在插件商店仓库补齐 market.json")
        return

    try:
        data = _download(item.url)
    except Exception as exc:
        await ctx.reply(f"下载失败：{exc}")
        return

    # verify sha256 if provided
    import hashlib

    got = hashlib.sha256(data).hexdigest()
    expected = (item.sha256 or "").strip()
    if expected and expected != got:
        await ctx.reply(
            "插件校验失败，已拒绝更新。\n" f"期望 sha256：{expected}\n" f"实际 sha256：{got}"
        )
        return

    filename = (old or {}).get("file") or (_safe_filename(item.name) + ".py")
    target = _plugins_dir() / filename
    target.write_bytes(data)

    installed.setdefault("installed", {})[item.name] = {
        "name": item.name,
        "file": target.name,
        "url": item.url,
        "version": item.version,
        "author": item.author,
        "sha256": got,
    }
    _save_installed(installed)

    before = (old or {}).get("version") or "?"
    await ctx.reply(
        "更新完成（已写入 user_plugins/）\n"
        f"插件：{item.name} {before} -> v{item.version}\n"
        f"文件：{target.name}\n"
        "提示：当前框架不支持热加载插件，需要重启服务后生效。"
    )


remove_cmd = CommandPlugin(
    name="plugin_market_remove",
    command="卸载插件",
    description="remove a plugin installed from market",
    meta=PluginMeta(name="plugin_market_remove", version="1.0.0", author="OpenClaw", description="卸载插件商店插件"),
)


@remove_cmd.handle
async def on_remove(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以卸载插件")
        return

    name = (ctx.args or "").strip()
    if not name:
        await ctx.reply("用法：卸载插件 插件名")
        return

    installed = _load_installed()
    info = (installed.get("installed", {}) or {}).get(name)
    if not info:
        await ctx.reply("未找到已安装记录。先看：已装插件")
        return

    # Safe removal: rename file to .disabled (keeps rollback), and disable in registry.
    file = info.get("file")
    if file:
        p = _plugins_dir() / str(file)
        if p.exists():
            disabled = p.with_suffix(p.suffix + ".disabled")
            try:
                p.rename(disabled)
            except Exception:
                pass

    (installed.get("installed", {}) or {}).pop(name, None)
    _save_installed(installed)

    await ctx.reply(
        "卸载完成（已安全停用文件，保留可回滚）\n"
        f"插件：{name}\n"
        "提示：当前框架不支持热加载插件，需要重启服务后生效。"
    )


# expose plugins
plugins = [market_cmd, installed_cmd, update_cmd, remove_cmd]
