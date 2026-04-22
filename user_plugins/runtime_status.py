from __future__ import annotations

import time

from app.core.plugin import CommandPlugin, PluginMeta
from app.auth import is_owner
from app.config import settings


plugin = CommandPlugin(
    name="runtime_status",
    command="运行状态",
    description="查看机器人运行状态（OneBot/NapCat 在线、版本、配置摘要）",
    meta=PluginMeta(
        name="runtime_status",
        version="0.1.0",
        author="openclaw",
        description="Owner-only runtime status command.",
    ),
)


@plugin.handle
async def handle(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("权限不足（仅主人可用）")
        return

    lines = []
    lines.append("【运行状态】")
    lines.append(f"app={settings.app_name}")
    lines.append(f"adapter={settings.adapter}")
    # framework VERSION file (best-effort)
    try:
        from pathlib import Path

        ver = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        ver = ""
    if ver:
        lines.append(f"version={ver}")
    lines.append(f"onebot_api={settings.onebot_api_base}")
    lines.append(f"public_base={settings.public_base_url}")
    lines.append(f"card_mode_global={settings.card_mode}")

    # OneBot status
    try:
        st = await ctx.api.get_status()
        data = st.get("data") if isinstance(st, dict) else {}
        online = data.get("online")
        good = data.get("good")
        lines.append(f"onebot_online={online} good={good}")
    except Exception as e:
        lines.append(f"onebot_online=error ({type(e).__name__})")

    # context info
    if ctx.is_group:
        lines.append(f"chat=group group_id={ctx.group_id}")
    else:
        lines.append(f"chat=private user_id={ctx.user_id}")

    lines.append(f"ts={int(time.time())}")

    await ctx.reply("\n".join(filter(None, lines)))
