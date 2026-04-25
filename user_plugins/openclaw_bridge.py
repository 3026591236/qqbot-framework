from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta

plugin = None

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

OPENCLAW_BRIDGE_ENABLED = os.getenv("QQBOT_OPENCLAW_BRIDGE_ENABLED", "false").lower() == "true"
OPENCLAW_BRIDGE_BASE_URL = os.getenv("QQBOT_OPENCLAW_BRIDGE_BASE_URL", "").rstrip("/")
OPENCLAW_BRIDGE_API_KEY = os.getenv("QQBOT_OPENCLAW_BRIDGE_API_KEY", "")
OPENCLAW_BRIDGE_TIMEOUT = float(os.getenv("QQBOT_OPENCLAW_BRIDGE_TIMEOUT", "90"))
OPENCLAW_BRIDGE_ADMIN_IDS = set(filter(None, (x.strip() for x in os.getenv("QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS", "").split(","))))
OPENCLAW_BRIDGE_ALLOWED_ACTIONS = [x.strip() for x in os.getenv(
    "QQBOT_OPENCLAW_BRIDGE_ALLOWED_ACTIONS",
    "xiaoxiao3d,weather,github,session_send"
).split(",") if x.strip()]
OPENCLAW_BRIDGE_COMMAND = os.getenv("QQBOT_OPENCLAW_BRIDGE_COMMAND", "小小")
OPENCLAW_BRIDGE_DEFAULT_SESSION = os.getenv("QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION", "")
OPENCLAW_BRIDGE_ALLOW_GROUP = os.getenv("QQBOT_OPENCLAW_BRIDGE_ALLOW_GROUP", "true").lower() == "true"
OPENCLAW_BRIDGE_ALLOW_PRIVATE = os.getenv("QQBOT_OPENCLAW_BRIDGE_ALLOW_PRIVATE", "true").lower() == "true"


def _extract_after_command(ctx, command: str) -> str:
    text = (ctx.text or "").strip()
    variants = [command, f"/{command}"] if not command.startswith("/") else [command, command[1:]]
    for variant in variants:
        if text == variant:
            return ""
        prefix = variant + " "
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return ""


def _save_env_value(key: str, value: str) -> None:
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _allowed_scope(ctx) -> bool:
    if ctx.is_group:
        return OPENCLAW_BRIDGE_ALLOW_GROUP
    return OPENCLAW_BRIDGE_ALLOW_PRIVATE


def _is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    uid = str(user_id)
    return is_owner(user_id) or uid in OPENCLAW_BRIDGE_ADMIN_IDS


def _headers() -> dict[str, str]:
    if not OPENCLAW_BRIDGE_BASE_URL:
        raise RuntimeError("未配置 QQBOT_OPENCLAW_BRIDGE_BASE_URL")
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_BRIDGE_API_KEY:
        headers["Authorization"] = f"Bearer {OPENCLAW_BRIDGE_API_KEY}"
    return headers


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{OPENCLAW_BRIDGE_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=OPENCLAW_BRIDGE_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"raw": data}


async def _send_to_session(message: str, session_key: str = "") -> dict[str, Any]:
    target = session_key or OPENCLAW_BRIDGE_DEFAULT_SESSION
    if not target:
        raise RuntimeError("未配置默认 OpenClaw sessionKey")
    return await _post("/api/sessions/send", {
        "sessionKey": target,
        "message": message,
        "timeoutSeconds": 120,
    })


async def _run_action(action: str, args: str) -> str:
    action = (action or "").strip()
    if action not in OPENCLAW_BRIDGE_ALLOWED_ACTIONS:
        raise RuntimeError(f"不允许的动作：{action}")

    if action == "xiaoxiao3d":
        msg = "调用 xiaoxiao3d"
        if args:
            msg += f" {args}"
        result = await _send_to_session(msg)
    elif action == "weather":
        result = await _send_to_session(f"查询天气 {args}".strip())
    elif action == "github":
        result = await _send_to_session(f"GitHub {args}".strip())
    elif action == "session_send":
        result = await _send_to_session(args)
    else:
        raise RuntimeError(f"暂未实现动作：{action}")

    reply = result.get("reply") or result.get("message") or result.get("result") or result
    if isinstance(reply, dict):
        return json.dumps(reply, ensure_ascii=False)[:3000]
    return str(reply)[:3000]


openclaw_help = CommandPlugin(
    name="openclaw_bridge_help",
    command="OpenClaw帮助",
    description="show openclaw bridge help",
    meta=PluginMeta(name="openclaw_bridge_help", version="1.1.0", author="OpenClaw", description="OpenClaw 管理桥接帮助"),
)


@openclaw_help.handle
async def on_openclaw_help(ctx):
    await ctx.reply(
        "OpenClaw 管理桥接命令：\n"
        f"- {OPENCLAW_BRIDGE_COMMAND} 你的需求（固定直通指令）\n"
        "- OpenClaw状态\n"
        "- 设置OpenClaw管理员 QQ号\n"
        "- 删除OpenClaw管理员 QQ号\n"
        "- OpenClaw管理员列表\n"
        "- 配置OpenClaw桥接 地址 [Key] [sessionKey]（仅主人私聊）\n"
        "说明：固定指令后面的内容会原样转发给 OpenClaw，由 OpenClaw 执行后再回复回来。"
    )


openclaw_status = CommandPlugin(
    name="openclaw_bridge_status",
    command="OpenClaw状态",
    description="show openclaw bridge status",
    meta=PluginMeta(name="openclaw_bridge_status", version="1.0.0", author="OpenClaw", description="OpenClaw 管理桥接状态"),
)


@openclaw_status.handle
async def on_openclaw_status(ctx):
    if not _is_admin(ctx.user_id):
        await ctx.reply("没有权限")
        return
    enabled = OPENCLAW_BRIDGE_ENABLED and bool(OPENCLAW_BRIDGE_BASE_URL)
    masked_key = (OPENCLAW_BRIDGE_API_KEY[:6] + "***") if OPENCLAW_BRIDGE_API_KEY else "-"
    admins = "、".join(sorted(OPENCLAW_BRIDGE_ADMIN_IDS)) or "无"
    await ctx.reply(
        f"OpenClaw 桥接状态\n"
        f"启用：{'是' if enabled else '否'}\n"
        f"接口：{OPENCLAW_BRIDGE_BASE_URL or '-'}\n"
        f"Key：{masked_key}\n"
        f"默认会话：{OPENCLAW_BRIDGE_DEFAULT_SESSION or '-'}\n"
        f"管理员：{admins}\n"
        f"固定指令：{OPENCLAW_BRIDGE_COMMAND}\n"
        f"允许动作：{', '.join(OPENCLAW_BRIDGE_ALLOWED_ACTIONS) or '-'}"
    )


openclaw_direct = CommandPlugin(
    name="openclaw_bridge_direct",
    command=OPENCLAW_BRIDGE_COMMAND,
    description="send raw request to OpenClaw session via fixed command",
    meta=PluginMeta(name="openclaw_bridge_direct", version="1.1.0", author="OpenClaw", description="固定指令直通 OpenClaw"),
)


@openclaw_direct.handle
async def on_openclaw_direct(ctx):
    if not _is_admin(ctx.user_id):
        await ctx.reply("没有权限")
        return
    if not OPENCLAW_BRIDGE_ENABLED:
        await ctx.reply("OpenClaw 桥接未启用")
        return
    if not _allowed_scope(ctx):
        await ctx.reply("当前场景未开放 OpenClaw 桥接")
        return
    content = _extract_after_command(ctx, OPENCLAW_BRIDGE_COMMAND)
    if not content:
        await ctx.reply(f"用法：{OPENCLAW_BRIDGE_COMMAND} 你的需求")
        return
    try:
        reply = await _run_action("session_send", content)
    except Exception as exc:
        await ctx.reply(f"OpenClaw 调用失败：{exc}")
        return
    await ctx.reply(reply)


set_openclaw_admin = CommandPlugin(
    name="set_openclaw_admin",
    command="设置OpenClaw管理员",
    description="add openclaw bridge admin",
    meta=PluginMeta(name="set_openclaw_admin", version="1.0.0", author="OpenClaw", description="设置 OpenClaw 管理员"),
)


@set_openclaw_admin.handle
async def on_set_openclaw_admin(ctx):
    global OPENCLAW_BRIDGE_ADMIN_IDS
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以设置管理员")
        return
    qq = _extract_after_command(ctx, "设置OpenClaw管理员")
    if not qq or not qq.isdigit():
        await ctx.reply("用法：设置OpenClaw管理员 QQ号")
        return
    OPENCLAW_BRIDGE_ADMIN_IDS.add(qq)
    value = ",".join(sorted(OPENCLAW_BRIDGE_ADMIN_IDS))
    os.environ["QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS"] = value
    _save_env_value("QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS", value)
    await ctx.reply(f"已添加 OpenClaw 管理员：{qq}")


remove_openclaw_admin = CommandPlugin(
    name="remove_openclaw_admin",
    command="删除OpenClaw管理员",
    description="remove openclaw bridge admin",
    meta=PluginMeta(name="remove_openclaw_admin", version="1.0.0", author="OpenClaw", description="删除 OpenClaw 管理员"),
)


@remove_openclaw_admin.handle
async def on_remove_openclaw_admin(ctx):
    global OPENCLAW_BRIDGE_ADMIN_IDS
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以删除管理员")
        return
    qq = _extract_after_command(ctx, "删除OpenClaw管理员")
    if not qq or not qq.isdigit():
        await ctx.reply("用法：删除OpenClaw管理员 QQ号")
        return
    OPENCLAW_BRIDGE_ADMIN_IDS.discard(qq)
    value = ",".join(sorted(OPENCLAW_BRIDGE_ADMIN_IDS))
    os.environ["QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS"] = value
    _save_env_value("QQBOT_OPENCLAW_BRIDGE_ADMIN_IDS", value)
    await ctx.reply(f"已删除 OpenClaw 管理员：{qq}")


list_openclaw_admins = CommandPlugin(
    name="list_openclaw_admins",
    command="OpenClaw管理员列表",
    description="list openclaw bridge admins",
    meta=PluginMeta(name="list_openclaw_admins", version="1.0.0", author="OpenClaw", description="查看 OpenClaw 管理员列表"),
)


@list_openclaw_admins.handle
async def on_list_openclaw_admins(ctx):
    if not _is_admin(ctx.user_id):
        await ctx.reply("没有权限")
        return
    admins = "\n".join(f"- {x}" for x in sorted(OPENCLAW_BRIDGE_ADMIN_IDS)) or "- 无"
    await ctx.reply("OpenClaw 管理员列表：\n" + admins)


configure_openclaw = CommandPlugin(
    name="configure_openclaw_bridge",
    command="配置OpenClaw桥接",
    description="configure openclaw bridge",
    meta=PluginMeta(name="configure_openclaw_bridge", version="1.0.0", author="OpenClaw", description="配置 OpenClaw 桥接"),
)


@configure_openclaw.handle
async def on_configure_openclaw(ctx):
    global OPENCLAW_BRIDGE_ENABLED, OPENCLAW_BRIDGE_BASE_URL, OPENCLAW_BRIDGE_API_KEY, OPENCLAW_BRIDGE_DEFAULT_SESSION
    if ctx.is_group:
        await ctx.reply("这个命令只能在私聊里用")
        return
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以配置 OpenClaw 桥接")
        return
    raw = _extract_after_command(ctx, "配置OpenClaw桥接")
    parts = raw.split()
    if len(parts) < 1:
        await ctx.reply("用法：配置OpenClaw桥接 地址 [Key] [sessionKey]")
        return
    OPENCLAW_BRIDGE_BASE_URL = parts[0].strip().rstrip("/")
    OPENCLAW_BRIDGE_API_KEY = parts[1].strip() if len(parts) >= 2 else ""
    OPENCLAW_BRIDGE_DEFAULT_SESSION = parts[2].strip() if len(parts) >= 3 else OPENCLAW_BRIDGE_DEFAULT_SESSION
    OPENCLAW_BRIDGE_ENABLED = True

    os.environ["QQBOT_OPENCLAW_BRIDGE_ENABLED"] = "true"
    os.environ["QQBOT_OPENCLAW_BRIDGE_BASE_URL"] = OPENCLAW_BRIDGE_BASE_URL
    os.environ["QQBOT_OPENCLAW_BRIDGE_API_KEY"] = OPENCLAW_BRIDGE_API_KEY
    os.environ["QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION"] = OPENCLAW_BRIDGE_DEFAULT_SESSION

    _save_env_value("QQBOT_OPENCLAW_BRIDGE_ENABLED", "true")
    _save_env_value("QQBOT_OPENCLAW_BRIDGE_BASE_URL", OPENCLAW_BRIDGE_BASE_URL)
    _save_env_value("QQBOT_OPENCLAW_BRIDGE_API_KEY", OPENCLAW_BRIDGE_API_KEY)
    _save_env_value("QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION", OPENCLAW_BRIDGE_DEFAULT_SESSION)

    await ctx.reply(
        f"OpenClaw 桥接已保存并立即生效\n"
        f"接口：{OPENCLAW_BRIDGE_BASE_URL}\n"
        f"默认会话：{OPENCLAW_BRIDGE_DEFAULT_SESSION or '-'}\n"
        f"允许动作：{', '.join(OPENCLAW_BRIDGE_ALLOWED_ACTIONS)}"
    )


plugins = [
    openclaw_help,
    openclaw_status,
    openclaw_direct,
    set_openclaw_admin,
    remove_openclaw_admin,
    list_openclaw_admins,
    configure_openclaw,
]
