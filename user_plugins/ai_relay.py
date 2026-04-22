from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from app.auth import is_owner
from app.core.plugin import CommandPlugin, PluginMeta

plugin = None

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

AI_RELAY_ENABLED = os.getenv("QQBOT_AI_RELAY_ENABLED", "false").lower() == "true"
AI_RELAY_BASE_URL = os.getenv("QQBOT_AI_RELAY_BASE_URL", "").rstrip("/")
AI_RELAY_API_KEY = os.getenv("QQBOT_AI_RELAY_API_KEY", "")
AI_RELAY_MODEL = os.getenv("QQBOT_AI_RELAY_MODEL", "gpt-4o-mini")
AI_RELAY_TIMEOUT = float(os.getenv("QQBOT_AI_RELAY_TIMEOUT", "60"))
AI_RELAY_SYSTEM_PROMPT = os.getenv(
    "QQBOT_AI_RELAY_SYSTEM_PROMPT",
    "你是接入 QQ 机器人的 AI 助手。回答要简洁、直接、像真人，不要官腔。",
)
AI_RELAY_ALLOW_GROUP = os.getenv("QQBOT_AI_RELAY_ALLOW_GROUP", "true").lower() == "true"
AI_RELAY_ALLOW_PRIVATE = os.getenv("QQBOT_AI_RELAY_ALLOW_PRIVATE", "true").lower() == "true"
AI_RELAY_MAX_INPUT = int(os.getenv("QQBOT_AI_RELAY_MAX_INPUT", "2000"))
LAST_MODELS: list[str] = []


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


def _is_allowed_scope(ctx) -> bool:
    if ctx.is_group:
        return AI_RELAY_ALLOW_GROUP
    return AI_RELAY_ALLOW_PRIVATE


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


def _normalize_base_url(url: str) -> str:
    value = url.strip().rstrip("/")
    if not value:
        return value
    if not value.endswith("/v1"):
        value = value + "/v1"
    return value


def _build_headers() -> dict[str, str]:
    if not AI_RELAY_BASE_URL:
        raise RuntimeError("未配置 QQBOT_AI_RELAY_BASE_URL")
    if not AI_RELAY_API_KEY:
        raise RuntimeError("未配置 QQBOT_AI_RELAY_API_KEY")
    return {
        "Authorization": f"Bearer {AI_RELAY_API_KEY}",
        "Content-Type": "application/json",
    }


async def _fetch_models() -> list[str]:
    headers = _build_headers()
    url = f"{AI_RELAY_BASE_URL}/models"
    async with httpx.AsyncClient(timeout=AI_RELAY_TIMEOUT) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("data") or []
    models: list[str] = []
    for item in items:
        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.strip():
                models.append(model_id.strip())
    if not models:
        raise RuntimeError(f"未获取到模型列表：{data}")
    return models


async def _chat_once(user_text: str) -> str:
    headers = _build_headers()
    url = f"{AI_RELAY_BASE_URL}/chat/completions"
    payload: dict[str, Any] = {
        "model": AI_RELAY_MODEL,
        "messages": [
            {"role": "system", "content": AI_RELAY_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=AI_RELAY_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"中转站返回异常：{data}")

    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text")
                if isinstance(txt, str) and txt.strip():
                    text_parts.append(txt.strip())
        if text_parts:
            return "\n".join(text_parts)

    raise RuntimeError(f"中转站没有返回有效文本：{data}")


ai_help = CommandPlugin(
    name="ai_relay_help",
    command="AI帮助",
    description="show ai relay help",
    meta=PluginMeta(name="ai_relay_help", version="1.0.0", author="OpenClaw", description="AI 中转站帮助"),
)


@ai_help.handle
async def on_ai_help(ctx):
    await ctx.reply(
        "AI 中转站命令：\n"
        "- AI帮助\n"
        "- AI状态\n"
        "- AI 你的问题\n"
        "- 问AI 你的问题\n"
        "- 配置AI中转站 地址 Key（仅主人私聊）\n"
        "- AI模型列表（仅主人私聊）\n"
        "- 选择AI模型 序号\n"
        "- 切换AI模型 模型名（仅主人）\n"
        "说明：插件按 OpenAI 兼容接口对接中转站。"
    )


ai_status = CommandPlugin(
    name="ai_relay_status",
    command="AI状态",
    description="show ai relay status",
    meta=PluginMeta(name="ai_relay_status", version="1.0.0", author="OpenClaw", description="AI 中转站状态"),
)


@ai_status.handle
async def on_ai_status(ctx):
    enabled = AI_RELAY_ENABLED and bool(AI_RELAY_BASE_URL and AI_RELAY_API_KEY)
    masked_key = (AI_RELAY_API_KEY[:6] + "***") if AI_RELAY_API_KEY else "-"
    await ctx.reply(
        f"AI 中转站状态\n"
        f"启用：{'是' if enabled else '否'}\n"
        f"接口：{AI_RELAY_BASE_URL or '-'}\n"
        f"模型：{AI_RELAY_MODEL}\n"
        f"Key：{masked_key}\n"
        f"群聊可用：{'是' if AI_RELAY_ALLOW_GROUP else '否'}\n"
        f"私聊可用：{'是' if AI_RELAY_ALLOW_PRIVATE else '否'}"
    )


ai_ask = CommandPlugin(
    name="ai_relay_ask",
    command="AI",
    description="ask ai relay",
    meta=PluginMeta(name="ai_relay_ask", version="1.0.0", author="OpenClaw", description="AI 中转站问答"),
)


@ai_ask.handle
async def on_ai_ask(ctx):
    if not AI_RELAY_ENABLED:
        await ctx.reply("AI 中转站插件未启用，请先配置 QQBOT_AI_RELAY_* 环境变量")
        return
    if not _is_allowed_scope(ctx):
        await ctx.reply("当前场景未开放 AI 对话")
        return
    prompt = _extract_after_command(ctx, "AI")
    if not prompt:
        await ctx.reply("用法：AI 你的问题")
        return
    if len(prompt) > AI_RELAY_MAX_INPUT:
        await ctx.reply(f"输入太长了，最多 {AI_RELAY_MAX_INPUT} 个字符")
        return
    try:
        reply = await _chat_once(prompt)
    except Exception as exc:
        await ctx.reply(f"AI 中转站调用失败：{exc}")
        return
    await ctx.reply(reply[:4000])


ask_ai = CommandPlugin(
    name="ask_ai_alias",
    command="问AI",
    description="ask ai relay alias",
    meta=PluginMeta(name="ask_ai_alias", version="1.0.0", author="OpenClaw", description="AI 中转站问答别名"),
)


@ask_ai.handle
async def on_ask_ai(ctx):
    if not AI_RELAY_ENABLED:
        await ctx.reply("AI 中转站插件未启用，请先配置 QQBOT_AI_RELAY_* 环境变量")
        return
    if not _is_allowed_scope(ctx):
        await ctx.reply("当前场景未开放 AI 对话")
        return
    prompt = _extract_after_command(ctx, "问AI")
    if not prompt:
        await ctx.reply("用法：问AI 你的问题")
        return
    if len(prompt) > AI_RELAY_MAX_INPUT:
        await ctx.reply(f"输入太长了，最多 {AI_RELAY_MAX_INPUT} 个字符")
        return
    try:
        reply = await _chat_once(prompt)
    except Exception as exc:
        await ctx.reply(f"AI 中转站调用失败：{exc}")
        return
    await ctx.reply(reply[:4000])


configure_ai = CommandPlugin(
    name="ai_relay_configure",
    command="配置AI中转站",
    description="configure ai relay in private chat",
    meta=PluginMeta(name="ai_relay_configure", version="1.1.0", author="OpenClaw", description="配置 AI 中转站"),
)


@configure_ai.handle
async def on_configure_ai(ctx):
    global AI_RELAY_ENABLED, AI_RELAY_BASE_URL, AI_RELAY_API_KEY, AI_RELAY_MODEL
    if ctx.is_group:
        await ctx.reply("这个命令只能在私聊里用")
        return
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以配置 AI 中转站")
        return
    raw = _extract_after_command(ctx, "配置AI中转站")
    parts = raw.split()
    if len(parts) < 2:
        await ctx.reply("用法：配置AI中转站 地址 Key\n示例：配置AI中转站 https://api.example.com/v1 sk-xxxx")
        return

    base_url = _normalize_base_url(parts[0])
    api_key = parts[1].strip()

    AI_RELAY_BASE_URL = base_url
    AI_RELAY_API_KEY = api_key
    AI_RELAY_ENABLED = True

    os.environ["QQBOT_AI_RELAY_BASE_URL"] = AI_RELAY_BASE_URL
    os.environ["QQBOT_AI_RELAY_API_KEY"] = AI_RELAY_API_KEY
    os.environ["QQBOT_AI_RELAY_ENABLED"] = "true"

    _save_env_value("QQBOT_AI_RELAY_BASE_URL", AI_RELAY_BASE_URL)
    _save_env_value("QQBOT_AI_RELAY_API_KEY", AI_RELAY_API_KEY)
    _save_env_value("QQBOT_AI_RELAY_ENABLED", "true")

    await ctx.reply(
        f"AI 中转站已保存并立即生效\n"
        f"接口：{AI_RELAY_BASE_URL}\n"
        f"Key：{AI_RELAY_API_KEY[:6]}***\n"
        f"当前默认模型：{AI_RELAY_MODEL}\n"
        f"下一步可发送：AI模型列表"
    )


model_list = CommandPlugin(
    name="ai_relay_model_list",
    command="AI模型列表",
    description="list models from ai relay",
    meta=PluginMeta(name="ai_relay_model_list", version="1.1.0", author="OpenClaw", description="获取 AI 模型列表"),
)


@model_list.handle
async def on_model_list(ctx):
    global LAST_MODELS
    if ctx.is_group:
        await ctx.reply("这个命令只能在私聊里用")
        return
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以查看 AI 模型列表")
        return
    if not AI_RELAY_ENABLED:
        await ctx.reply("AI 中转站未启用，请先配置")
        return
    try:
        models = await _fetch_models()
        LAST_MODELS = models
    except Exception as exc:
        await ctx.reply(f"获取模型列表失败：{exc}")
        return
    preview = models[:50]
    await ctx.reply(
        "可用模型列表：\n" + "\n".join(f"{idx}. {name}" for idx, name in enumerate(preview, start=1)) +
        ("\n（模型较多，仅显示前 50 个）" if len(models) > 50 else "") +
        "\n可发送：选择AI模型 序号"
    )


select_model = CommandPlugin(
    name="ai_relay_select_model",
    command="选择AI模型",
    description="select model by index from last model list",
    meta=PluginMeta(name="ai_relay_select_model", version="1.2.0", author="OpenClaw", description="按序号选择 AI 模型"),
)


@select_model.handle
async def on_select_model(ctx):
    global AI_RELAY_MODEL
    if ctx.is_group:
        await ctx.reply("这个命令只能在私聊里用")
        return
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以选择 AI 模型")
        return
    raw = _extract_after_command(ctx, "选择AI模型")
    if not raw.isdigit():
        await ctx.reply("用法：选择AI模型 序号")
        return
    if not LAST_MODELS:
        await ctx.reply("还没有可选模型列表，请先发送：AI模型列表")
        return
    idx = int(raw)
    if idx < 1 or idx > len(LAST_MODELS):
        await ctx.reply(f"序号超出范围，可选范围：1-{len(LAST_MODELS)}")
        return
    AI_RELAY_MODEL = LAST_MODELS[idx - 1]
    os.environ["QQBOT_AI_RELAY_MODEL"] = AI_RELAY_MODEL
    _save_env_value("QQBOT_AI_RELAY_MODEL", AI_RELAY_MODEL)
    await ctx.reply(f"已选择 AI 模型：{AI_RELAY_MODEL}")


switch_model = CommandPlugin(
    name="ai_relay_switch_model",
    command="切换AI模型",
    description="switch ai relay model for current process",
    meta=PluginMeta(name="ai_relay_switch_model", version="1.0.0", author="OpenClaw", description="切换 AI 模型"),
)


@switch_model.handle
async def on_switch_model(ctx):
    global AI_RELAY_MODEL
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以切换 AI 模型")
        return
    model = _extract_after_command(ctx, "切换AI模型")
    if not model:
        await ctx.reply("用法：切换AI模型 模型名")
        return
    AI_RELAY_MODEL = model
    os.environ["QQBOT_AI_RELAY_MODEL"] = AI_RELAY_MODEL
    _save_env_value("QQBOT_AI_RELAY_MODEL", AI_RELAY_MODEL)
    await ctx.reply(f"已切换 AI 模型：{AI_RELAY_MODEL}")
