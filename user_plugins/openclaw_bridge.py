from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
from pathlib import Path
import re
from typing import Any

from app.adapters.onebot import OneBotAPI

IMAGE_URL_RE = re.compile(r"https?://[^\s<>'\"]+?(?:\.png|\.jpg|\.jpeg|\.gif|\.webp)(?:\?[^\s<>'\"]*)?", re.IGNORECASE)
GENERIC_IMAGE_HOST_RE = re.compile(r"https?://[^\s<>'\"]*(?:picsum\.photos|placehold\.co|images\.unsplash\.com)[^\s<>'\"]*", re.IGNORECASE)

import httpx

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta, RegexPlugin

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
OPENCLAW_BRIDGE_COMMAND = os.getenv("QQBOT_OPENCLAW_BRIDGE_COMMAND", "爪爪")
OPENCLAW_BRIDGE_ALIASES = [x.strip() for x in os.getenv("QQBOT_OPENCLAW_BRIDGE_ALIASES", "小小").split(",") if x.strip()]
OPENCLAW_BRIDGE_DEFAULT_SESSION = os.getenv("QQBOT_OPENCLAW_BRIDGE_DEFAULT_SESSION", "")
OPENCLAW_BRIDGE_ALLOW_GROUP = os.getenv("QQBOT_OPENCLAW_BRIDGE_ALLOW_GROUP", "true").lower() == "true"
OPENCLAW_BRIDGE_ALLOW_PRIVATE = os.getenv("QQBOT_OPENCLAW_BRIDGE_ALLOW_PRIVATE", "true").lower() == "true"
OPENCLAW_BRIDGE_CONTINUE_PRIVATE = os.getenv("QQBOT_OPENCLAW_BRIDGE_CONTINUE_PRIVATE", "true").lower() == "true"
OPENCLAW_BRIDGE_CONTINUE_GROUP = os.getenv("QQBOT_OPENCLAW_BRIDGE_CONTINUE_GROUP", "true").lower() == "true"
OPENCLAW_BRIDGE_CONTINUE_WINDOW_SECONDS = int(os.getenv("QQBOT_OPENCLAW_BRIDGE_CONTINUE_WINDOW_SECONDS", "600"))

_CONTINUATION_STATE: dict[str, float] = {}
_ACTIVE_WATCHES: dict[str, dict[str, Any]] = {}
_RECENT_TASK_STATE: dict[str, float] = {}
_RECENT_TASK_WINDOW_SECONDS = 600
_RESERVED_COMMAND_PREFIXES = [
    "OpenClaw帮助",
    "OpenClaw状态",
    "设置OpenClaw管理员",
    "删除OpenClaw管理员",
    "OpenClaw管理员列表",
    "配置OpenClaw桥接",
]
_CONTINUATION_EXIT_WORDS = {"退出", "结束", "关闭", "停止", "退出小小", "结束小小", "关闭小小", "停止小小", "退出爪爪", "结束爪爪", "关闭爪爪", "停止爪爪"}


def _normalize_command_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    text = text.replace("\u3000", " ")
    parts = [part.strip() for part in text.splitlines() if part.strip()]
    text = " ".join(parts).strip()
    while text.startswith("[CQ:at,"):
        end = text.find("]")
        if end == -1:
            break
        text = text[end + 1:].lstrip()
    return text


def _is_pure_text_message(ctx) -> bool:
    raw_message = ctx.raw_event.get("message")
    if isinstance(raw_message, str):
        normalized = _normalize_command_text(raw_message)
        return bool(normalized) and "[CQ:" not in raw_message and "[CQ:" not in normalized
    if isinstance(raw_message, list):
        return len(raw_message) == 1 and isinstance(raw_message[0], dict) and raw_message[0].get("type") == "text"
    text = _normalize_command_text(ctx.text or "")
    return bool(text) and "[CQ:" not in text


def _extract_image_urls(ctx) -> list[str]:
    urls: list[str] = []
    raw_message = ctx.raw_event.get("message")
    if isinstance(raw_message, list):
        for item in raw_message:
            if not isinstance(item, dict) or item.get("type") != "image":
                continue
            data = item.get("data") or {}
            if not isinstance(data, dict):
                continue
            url = data.get("url") or data.get("file")
            if isinstance(url, str) and url.strip():
                urls.append(html.unescape(url.strip()))
    elif isinstance(raw_message, str):
        for match in re.finditer(r"\[CQ:image,[^\]]*url=([^,\]]+)", raw_message):
            url = html.unescape(match.group(1).strip())
            if url:
                urls.append(url)
    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def _build_openclaw_payload(ctx, content: str) -> str:
    content = (content or "").strip()
    image_urls = _extract_image_urls(ctx)
    if not image_urls:
        return content
    if content:
        return content
    return "请结合我发送的图片一起处理。"


def _active_watch_key(ctx) -> str:
    if ctx.user_id is None:
        return ""
    if ctx.is_group:
        if ctx.group_id is None:
            return ""
        return f"group:{ctx.group_id}:user:{ctx.user_id}"
    return f"private:{ctx.user_id}"


def _has_active_watch(ctx) -> bool:
    key = _active_watch_key(ctx)
    if not key:
        return False
    if key in _ACTIVE_WATCHES:
        return True
    expires_at = _RECENT_TASK_STATE.get(key)
    if not expires_at:
        return False
    if expires_at < asyncio.get_event_loop().time():
        _RECENT_TASK_STATE.pop(key, None)
        return False
    return True


def _touch_recent_task(ctx) -> None:
    key = _active_watch_key(ctx)
    if not key:
        return
    _RECENT_TASK_STATE[key] = asyncio.get_event_loop().time() + _RECENT_TASK_WINDOW_SECONDS


def _build_openclaw_attachments(ctx) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    for url in _extract_image_urls(ctx):
        attachments.append({"url": url, "mimeType": "image/png"})
    return attachments


def _extract_image_urls_from_text(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    normalized = text.replace("`", " ").replace("（", "(").replace("）", ")")
    urls: list[str] = []
    urls.extend(match.group(0).rstrip(')】>」』,.，`') for match in IMAGE_URL_RE.finditer(normalized))
    urls.extend(match.group(0).rstrip(')】>」』,.，`') for match in GENERIC_IMAGE_HOST_RE.finditer(normalized))
    deduped: list[str] = []
    for url in urls:
        if url and url not in deduped:
            deduped.append(url)
    return deduped


def _command_variants() -> list[str]:
    commands: list[str] = []
    for cmd in [OPENCLAW_BRIDGE_COMMAND, *OPENCLAW_BRIDGE_ALIASES]:
        cmd = (cmd or "").strip()
        if cmd and cmd not in commands:
            commands.append(cmd)
    return commands


def _extract_after_command(ctx, command: str | None = None) -> str:
    text = _normalize_command_text(ctx.text or "")
    variants: list[str] = []
    for cmd in ([command] if command else _command_variants()):
        if not cmd:
            continue
        if cmd.startswith("/"):
            variants.extend([cmd, cmd[1:]])
        else:
            variants.extend([cmd, f"/{cmd}"])
    deduped: list[str] = []
    for variant in variants:
        if variant not in deduped:
            deduped.append(variant)
    for variant in deduped:
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


def _continuation_key(ctx) -> str:
    if ctx.user_id is None:
        return ""
    if ctx.is_group:
        if not OPENCLAW_BRIDGE_CONTINUE_GROUP or ctx.group_id is None:
            return ""
        return f"group:{ctx.group_id}:user:{ctx.user_id}"
    if not OPENCLAW_BRIDGE_CONTINUE_PRIVATE:
        return ""
    return f"private:{ctx.user_id}"


def _continuation_active(ctx) -> bool:
    key = _continuation_key(ctx)
    if not key:
        return False
    expires_at = _CONTINUATION_STATE.get(key)
    if not expires_at:
        return False
    if expires_at < asyncio.get_event_loop().time():
        _CONTINUATION_STATE.pop(key, None)
        return False
    return True


def _touch_continuation(ctx) -> None:
    key = _continuation_key(ctx)
    if not key:
        return
    _CONTINUATION_STATE[key] = asyncio.get_event_loop().time() + OPENCLAW_BRIDGE_CONTINUE_WINDOW_SECONDS


def _clear_continuation(ctx) -> None:
    key = _continuation_key(ctx)
    if key:
        _CONTINUATION_STATE.pop(key, None)


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


def _target_session(session_key: str = "") -> str:
    target = session_key or OPENCLAW_BRIDGE_DEFAULT_SESSION
    if not target:
        raise RuntimeError("未配置默认 OpenClaw sessionKey")
    return target


async def _send_to_session(message: str, session_key: str = "", attachments: list[dict[str, str]] | None = None) -> dict[str, Any]:
    target = _target_session(session_key)
    print(f"[openclaw_bridge] target_session={target} message={message[:120]!r} attachments={len(attachments or [])}")
    payload = {
        "sessionKey": target,
        "message": message,
        "timeoutSeconds": 120,
    }
    if attachments:
        payload["attachments"] = attachments
    return await _post("/api/sessions/send", payload)


async def _start_watch(session_key: str = "", timeout_seconds: float = 600) -> dict[str, Any]:
    target = _target_session(session_key)
    return await _post("/api/watch/start", {"sessionKey": target, "timeoutSeconds": timeout_seconds})


def _watch_is_active(info: dict[str, Any] | None) -> bool:
    if not isinstance(info, dict):
        return False
    task = info.get("task")
    if task is None:
        return False
    return not task.done()


async def _poll_watch(watch_id: str) -> dict[str, Any]:
    url = f"{OPENCLAW_BRIDGE_BASE_URL}/api/watch/{watch_id}"
    async with httpx.AsyncClient(timeout=OPENCLAW_BRIDGE_TIMEOUT) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"raw": data}


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


_OPENCLAW_BRIDGE_COMMAND_PATTERN = "|".join(re.escape(x) for x in _command_variants())

openclaw_direct = RegexPlugin(
    name="openclaw_bridge_direct",
    pattern=rf"^(?:\[CQ:at,[^\]]+\]\s*)*(?:/)?(?:{_OPENCLAW_BRIDGE_COMMAND_PATTERN})(?:\s+.*)?$",
    description="send raw request to OpenClaw session via fixed command",
    meta=PluginMeta(name="openclaw_bridge_direct", version="1.4.0", author="OpenClaw", description="固定指令直通 OpenClaw"),
)


async def _download_image_for_reply(url: str) -> str:
    safe_url = (url or "").strip()
    if not safe_url:
        raise RuntimeError("empty image url")
    suffix = Path(safe_url.split("?", 1)[0]).suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        suffix = ".png"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(safe_url)
        resp.raise_for_status()
        content = resp.content
    filename = f"openclaw_reply_{hashlib.md5((safe_url + ':' + str(len(content)) + ':' + hashlib.md5(content).hexdigest()).encode('utf-8')).hexdigest()}{suffix}"
    target = Path('/tmp') / filename
    target.write_bytes(content)
    print(f"[openclaw_bridge] downloaded_image url={safe_url!r} target={str(target)!r} size={len(content)} head={content[:10]!r}")
    return str(target)


async def _deliver_watch_result(api: OneBotAPI, watch: dict[str, Any]) -> None:
    image_urls = watch.get("imageUrls") or []
    reply = watch.get("reply") or watch.get("message") or watch.get("result")
    sent = False
    discovered_from_text: list[str] = []
    if isinstance(reply, str):
        discovered_from_text = _extract_image_urls_from_text(reply)
    all_image_urls: list[str] = []
    if isinstance(image_urls, list):
        all_image_urls.extend(x for x in image_urls if isinstance(x, str) and x.strip())
    all_image_urls.extend(x for x in discovered_from_text if x not in all_image_urls)

    user_id = watch.get("user_id")
    group_id = watch.get("group_id")
    is_group = bool(watch.get("is_group") and group_id)

    for image_url in all_image_urls:
        try:
            local_file = await _download_image_for_reply(image_url.strip())
            print(f"[openclaw_bridge] deliver_image local_file={local_file!r} from={image_url!r} is_group={is_group}")
            if is_group:
                await api.send_group_image(int(group_id), local_file)
            elif user_id:
                await api.send_private_image(int(user_id), local_file)
            sent = True
        except Exception as exc:
            print(f"[openclaw_bridge] deliver_image_failed url={image_url!r} error={exc}")
            if is_group:
                await api.send_group_msg(int(group_id), image_url.strip())
            elif user_id:
                await api.send_private_msg(int(user_id), image_url.strip())
            sent = True

    if reply:
        reply_text = str(reply)[:3000]
        if discovered_from_text:
            for image_url in discovered_from_text:
                reply_text = reply_text.replace(image_url, "").replace(f"`{image_url}`", "").strip()
        reply_text = reply_text.strip("` \n")
        if reply_text:
            if is_group:
                await api.send_group_msg(int(group_id), reply_text)
            elif user_id:
                await api.send_private_msg(int(user_id), reply_text)
            sent = True

    if not sent:
        if is_group:
            await api.send_group_msg(int(group_id), "已执行，但没有可返回的文本或图片")
        elif user_id:
            await api.send_private_msg(int(user_id), "已执行，但没有可返回的文本或图片")


async def _watch_and_push(key: str, api: OneBotAPI, watch_id: str) -> None:
    should_clear_active = True
    try:
        while True:
            result = await _poll_watch(watch_id)
            state = str(result.get("state") or "unknown")
            if result.get("done"):
                merged = _ACTIVE_WATCHES.get(key, {}) | result
                await _deliver_watch_result(api, merged)
                if merged.get("waitingForUser"):
                    should_clear_active = False
                break
            if state in {"failed", "cancelled", "timeout"}:
                await _deliver_watch_result(api, _ACTIVE_WATCHES.get(key, {}) | result)
                break
            await asyncio.sleep(2)
    except Exception as exc:
        watch = _ACTIVE_WATCHES.get(key, {})
        user_id = watch.get("user_id")
        group_id = watch.get("group_id")
        is_group = bool(watch.get("is_group") and group_id)
        text = f"OpenClaw 监控失败：{exc}"
        if is_group:
            await api.send_group_msg(int(group_id), text)
        elif user_id:
            await api.send_private_msg(int(user_id), text)
    finally:
        watch = _ACTIVE_WATCHES.get(key)
        if isinstance(watch, dict):
            _RECENT_TASK_STATE[key] = asyncio.get_event_loop().time() + _RECENT_TASK_WINDOW_SECONDS
        if should_clear_active:
            _ACTIVE_WATCHES.pop(key, None)


async def _handle_openclaw_chat(ctx, content: str, attachments: list[dict[str, str]] | None = None) -> None:
    try:
        result = await _send_to_session(content, attachments=attachments)
    except Exception as exc:
        await ctx.reply(f"OpenClaw 调用失败：{exc}")
        return
    _touch_continuation(ctx)
    _touch_recent_task(ctx)
    print(f"[openclaw_bridge] continuation_touch key={_continuation_key(ctx)!r} text={content[:80]!r}")
    await _deliver_watch_result(ctx.api, {
        "user_id": ctx.user_id,
        "group_id": ctx.group_id,
        "is_group": ctx.is_group,
        **result,
    })

    try:
        key = _active_watch_key(ctx) or _continuation_key(ctx) or f"msg:{ctx.message_type}:{ctx.group_id or 0}:{ctx.user_id or 0}"
        existing = _ACTIVE_WATCHES.get(key)
        if _watch_is_active(existing):
            print(f"[openclaw_bridge] watch_reuse key={key!r} watch_id={existing.get('watchId')}")
            return
        watch_started = await _start_watch(timeout_seconds=600)
        watch_id = str(watch_started.get("watchId") or "").strip()
        if watch_id:
            task = asyncio.create_task(_watch_and_push(key, ctx.api, watch_id))
            _ACTIVE_WATCHES[key] = {
                "watchId": watch_id,
                "user_id": ctx.user_id,
                "group_id": ctx.group_id,
                "is_group": ctx.is_group,
                "task": task,
            }
            print(f"[openclaw_bridge] watch_started key={key!r} watch_id={watch_id}")
    except Exception as exc:
        print(f"[openclaw_bridge] watch_start_failed error={exc}")


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
    content = _extract_after_command(ctx)
    if not content:
        aliases = " / ".join(_command_variants())
        await ctx.reply(f"用法：{aliases} 你的需求")
        return
    await _handle_openclaw_chat(ctx, _build_openclaw_payload(ctx, content), _build_openclaw_attachments(ctx))


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


openclaw_continue = RegexPlugin(
    name="openclaw_bridge_continue",
    pattern=r"^.+$",
    description="continue private openclaw chat without wake word",
    meta=PluginMeta(name="openclaw_bridge_continue", version="1.0.0", author="OpenClaw", description="私聊连续对话接管"),
)


@openclaw_continue.handle
async def on_openclaw_continue(ctx):
    if not _is_admin(ctx.user_id):
        return
    if not OPENCLAW_BRIDGE_ENABLED or not _allowed_scope(ctx):
        return
    text = _normalize_command_text(ctx.text or "")
    image_urls = _extract_image_urls(ctx)
    if not text and not image_urls:
        return
    if not _is_pure_text_message(ctx) and not image_urls:
        print(f"[openclaw_bridge] continuation_skip_non_text key={_continuation_key(ctx)!r} raw={ctx.raw_event.get('message')!r}")
        return
    has_active_watch = _has_active_watch(ctx)
    if ctx.is_group and not OPENCLAW_BRIDGE_CONTINUE_GROUP and not has_active_watch:
        print(f"[openclaw_bridge] continuation_skip_group_disabled key={_continuation_key(ctx)!r} text={text[:80]!r} active_watch={has_active_watch}")
        return
    normalized_full = _normalize_command_text(ctx.text or "")
    command_used = normalized_full in _command_variants() or any(normalized_full.startswith(f"{cmd} ") or normalized_full.startswith(f"/{cmd} ") for cmd in _command_variants())
    if command_used:
        return
    if any(normalized_full == prefix or normalized_full.startswith(prefix + " ") for prefix in _RESERVED_COMMAND_PREFIXES):
        print(f"[openclaw_bridge] continuation_reserved_command text={normalized_full[:80]!r}")
        return
    if text in _CONTINUATION_EXIT_WORDS:
        _clear_continuation(ctx)
        print(f"[openclaw_bridge] continuation_clear key={_continuation_key(ctx)!r}")
        await ctx.reply("已退出小小连续对话")
        return
    if not _continuation_active(ctx) and not (ctx.is_group and has_active_watch):
        print(f"[openclaw_bridge] continuation_inactive key={_continuation_key(ctx)!r} text={text[:80]!r} active_watch={has_active_watch}")
        return
    payload_text = _build_openclaw_payload(ctx, text)
    payload_attachments = _build_openclaw_attachments(ctx)
    print(f"[openclaw_bridge] continuation_hit key={_continuation_key(ctx)!r} text={payload_text[:80]!r} attachments={len(payload_attachments)}")
    await _handle_openclaw_chat(ctx, payload_text, payload_attachments)


plugins = [
    openclaw_help,
    openclaw_status,
    openclaw_direct,
    openclaw_continue,
    set_openclaw_admin,
    remove_openclaw_admin,
    list_openclaw_admins,
    configure_openclaw,
]
