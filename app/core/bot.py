from __future__ import annotations

from typing import Any, Dict

from app.adapters.onebot import OneBotAPI
from app.config import settings
from app.core.context import MessageContext
from app.core.plugin import CommandPlugin, KeywordPlugin, RegexPlugin
from app.core.router import Router

try:
    from user_plugins.group_invite_guard import save_pending_invite
except Exception:  # optional plugin hook
    save_pending_invite = None

try:
    from user_plugins.cdk_rewards import process_invite_reward, process_random_speaker_message
except Exception:  # optional plugin hook
    process_invite_reward = None
    process_random_speaker_message = None


class BotApp:
    def __init__(self, api_base: str = "http://127.0.0.1:5700", adapter_name: str = "onebot") -> None:
        self.api = OneBotAPI(api_base)
        self.router = Router()

    def register_plugin(self, plugin: CommandPlugin | KeywordPlugin | RegexPlugin) -> None:
        self.router.register(plugin)

    async def handle_event(self, event: Dict[str, Any]) -> bool:
        post_type = event.get("post_type")
        if post_type == "request":
            return await self.handle_request_event(event)
        if post_type == "notice":
            return await self.handle_notice_event(event)
        if post_type != "message":
            return False

        raw_message = event.get("raw_message") or ""
        if not isinstance(raw_message, str):
            raw_message = str(raw_message)

        ctx = MessageContext(
            raw_event=event,
            text=raw_message.strip(),
            user_id=event.get("user_id"),
            group_id=event.get("group_id"),
            message_type=event.get("message_type", "private"),
            api=self.api,
        )
        if process_random_speaker_message is not None:
            try:
                await process_random_speaker_message(ctx)
            except Exception:
                pass
        return await self.router.dispatch(ctx)

    async def handle_notice_event(self, event: Dict[str, Any]) -> bool:
        if process_invite_reward is not None:
            try:
                handled = await process_invite_reward(self.api, event)
                if handled:
                    return True
            except Exception:
                pass
        return False

    async def handle_request_event(self, event: Dict[str, Any]) -> bool:
        if not settings.auto_notify_group_invite:
            return False
        if event.get("request_type") != "group":
            return False
        sub_type = str(event.get("sub_type") or "")
        if sub_type != "invite":
            return False
        flag = str(event.get("flag") or "")
        user_id = event.get("user_id")
        group_id = event.get("group_id")
        comment = str(event.get("comment") or "")
        if not flag:
            return False
        if save_pending_invite is not None:
            save_pending_invite(flag=flag, sub_type=sub_type, user_id=user_id, group_id=group_id, comment=comment)
        owner_ids = settings.owner_ids or []
        for owner_id in owner_ids:
            try:
                await self.api.send_private_msg(
                    int(owner_id),
                    "收到新的入群邀请\n"
                    f"群号：{group_id or '-'}\n"
                    f"邀请人：{user_id or '-'}\n"
                    f"附言：{comment or '-'}\n"
                    "如需同意，请回复：同意入群\n"
                    "如需拒绝，请回复：拒绝入群\n"
                    "也可以发送：入群邀请状态"
                )
            except Exception:
                continue
        return True
