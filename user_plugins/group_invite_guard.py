from __future__ import annotations

import json
from pathlib import Path

from app.auth import is_owner
from app.config import settings
from app.core.plugin import CommandPlugin, PluginMeta

STATE_FILE = Path(settings.data_dir) / "group_invite_pending.json"


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_pending_invite(*, flag: str, sub_type: str, user_id: int | None, group_id: int | None, comment: str = "") -> None:
    if not flag:
        return
    state = _load_state()
    state["pending"] = {
        "flag": str(flag),
        "sub_type": str(sub_type or "invite"),
        "user_id": user_id,
        "group_id": group_id,
        "comment": comment or "",
    }
    _save_state(state)


def get_pending_invite() -> dict:
    return _load_state().get("pending") or {}


def clear_pending_invite() -> None:
    state = _load_state()
    state.pop("pending", None)
    _save_state(state)


group_invite_status = CommandPlugin(
    name="group_invite_status",
    command="入群邀请状态",
    description="show pending group invite",
    meta=PluginMeta(name="group_invite_status", version="1.0.0", author="OpenClaw", description="查看待处理入群邀请"),
)


@group_invite_status.handle
async def on_group_invite_status(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以查看入群邀请状态")
        return
    pending = get_pending_invite()
    if not pending:
        await ctx.reply("当前没有待处理的入群邀请")
        return
    await ctx.reply(
        "当前有待处理的入群邀请\n"
        f"群号：{pending.get('group_id') or '-'}\n"
        f"邀请人：{pending.get('user_id') or '-'}\n"
        f"附言：{pending.get('comment') or '-'}\n"
        "回复：同意入群 或 拒绝入群"
    )


approve_group_invite = CommandPlugin(
    name="approve_group_invite",
    command="同意入群",
    description="approve pending group invite",
    meta=PluginMeta(name="approve_group_invite", version="1.0.0", author="OpenClaw", description="同意待处理入群邀请"),
)


@approve_group_invite.handle
async def on_approve_group_invite(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以处理入群邀请")
        return
    pending = get_pending_invite()
    if not pending:
        await ctx.reply("当前没有待处理的入群邀请")
        return
    try:
        await ctx.api.set_group_add_request(
            flag=str(pending.get("flag") or ""),
            sub_type=str(pending.get("sub_type") or "invite"),
            approve=True,
        )
        clear_pending_invite()
        await ctx.reply(f"已同意入群邀请，群号：{pending.get('group_id') or '-'}")
    except Exception as exc:
        await ctx.reply(f"处理入群邀请失败：{exc}")


reject_group_invite = CommandPlugin(
    name="reject_group_invite",
    command="拒绝入群",
    description="reject pending group invite",
    meta=PluginMeta(name="reject_group_invite", version="1.0.0", author="OpenClaw", description="拒绝待处理入群邀请"),
)


@reject_group_invite.handle
async def on_reject_group_invite(ctx):
    if not is_owner(ctx.user_id):
        await ctx.reply("只有主人可以处理入群邀请")
        return
    pending = get_pending_invite()
    if not pending:
        await ctx.reply("当前没有待处理的入群邀请")
        return
    try:
        await ctx.api.set_group_add_request(
            flag=str(pending.get("flag") or ""),
            sub_type=str(pending.get("sub_type") or "invite"),
            approve=False,
            reason="主人暂未同意",
        )
        clear_pending_invite()
        await ctx.reply(f"已拒绝入群邀请，群号：{pending.get('group_id') or '-'}")
    except Exception as exc:
        await ctx.reply(f"处理入群邀请失败：{exc}")
