from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.adapters.onebot import OneBotAPI
from app.card_mode import get_card_mode, render_text_to_card_images


@dataclass
class MessageContext:
    raw_event: Dict[str, Any]
    text: str
    user_id: int | None
    group_id: int | None
    message_type: str
    api: OneBotAPI

    @property
    def message_id(self) -> int | str | None:
        return self.raw_event.get("message_id")

    @property
    def sender(self) -> Dict[str, Any]:
        value = self.raw_event.get("sender")
        return value if isinstance(value, dict) else {}

    @property
    def role(self) -> str:
        role = self.sender.get("role")
        return str(role) if role is not None else "member"

    @property
    def is_group(self) -> bool:
        return self.message_type == "group" and self.group_id is not None

    @property
    def args(self) -> str:
        parts = self.text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    async def reply(self, message: str | list[dict]) -> None:
        if isinstance(message, str) and get_card_mode() == "image":
            image_urls = render_text_to_card_images(message)
            for image_url in image_urls:
                await self.reply_image(image_url)
            return

        if self.message_type == "group" and self.group_id is not None:
            await self.api.send_group_msg(self.group_id, message)
            return

        if self.user_id is not None:
            await self.api.send_private_msg(self.user_id, message)

    async def reply_json_card(self, data: str) -> None:
        if self.message_type == "group" and self.group_id is not None:
            await self.api.send_group_json(self.group_id, data)
            return
        if self.user_id is not None:
            await self.api.send_private_json(self.user_id, data)

    async def reply_xml_card(self, data: str) -> None:
        if self.message_type == "group" and self.group_id is not None:
            await self.api.send_group_xml(self.group_id, data)
            return
        if self.user_id is not None:
            await self.api.send_private_xml(self.user_id, data)

    async def reply_image(self, file: str) -> None:
        if self.message_type == "group" and self.group_id is not None:
            await self.api.send_group_image(self.group_id, file)
            return
        if self.user_id is not None:
            await self.api.send_private_image(self.user_id, file)

    async def reply_image_with_text(self, text: str, file: str) -> None:
        await self.reply([
            {"type": "text", "data": {"text": text}},
            {"type": "image", "data": {"file": file}},
        ])
