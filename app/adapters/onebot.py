from __future__ import annotations

import httpx


class OneBotAPI:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def get_status(self) -> dict:
        """OneBot get_status."""
        return await self._post("get_status", {})

    async def _post(self, action: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{self.base_url}/{action}", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def send_private_msg(self, user_id: int, message: str | list[dict]) -> dict:
        return await self._post("send_private_msg", {"user_id": user_id, "message": message})

    async def send_group_msg(self, group_id: int, message: str | list[dict]) -> dict:
        return await self._post("send_group_msg", {"group_id": group_id, "message": message})

    async def send_private_json(self, user_id: int, data: str) -> dict:
        return await self.send_private_msg(user_id, [{"type": "json", "data": {"data": data}}])

    async def send_group_json(self, group_id: int, data: str) -> dict:
        return await self.send_group_msg(group_id, [{"type": "json", "data": {"data": data}}])

    async def send_private_xml(self, user_id: int, data: str) -> dict:
        return await self.send_private_msg(user_id, [{"type": "xml", "data": {"data": data}}])

    async def send_group_xml(self, group_id: int, data: str) -> dict:
        return await self.send_group_msg(group_id, [{"type": "xml", "data": {"data": data}}])

    async def send_private_image(self, user_id: int, file: str) -> dict:
        return await self.send_private_msg(user_id, [{"type": "image", "data": {"file": file}}])

    async def send_group_image(self, group_id: int, file: str) -> dict:
        return await self.send_group_msg(group_id, [{"type": "image", "data": {"file": file}}])

    async def delete_msg(self, message_id: int | str) -> dict:
        return await self._post("delete_msg", {"message_id": message_id})

    async def set_group_ban(self, group_id: int, user_id: int, duration: int) -> dict:
        return await self._post("set_group_ban", {"group_id": group_id, "user_id": user_id, "duration": duration})

    async def set_group_whole_ban(self, group_id: int, enable: bool) -> dict:
        return await self._post("set_group_whole_ban", {"group_id": group_id, "enable": enable})

    async def set_group_kick(self, group_id: int, user_id: int, reject_add_request: bool = False) -> dict:
        return await self._post("set_group_kick", {"group_id": group_id, "user_id": user_id, "reject_add_request": reject_add_request})

    async def set_group_admin(self, group_id: int, user_id: int, enable: bool) -> dict:
        return await self._post("set_group_admin", {"group_id": group_id, "user_id": user_id, "enable": enable})

    async def set_group_card(self, group_id: int, user_id: int, card: str) -> dict:
        return await self._post("set_group_card", {"group_id": group_id, "user_id": user_id, "card": card})

    async def set_group_name(self, group_id: int, group_name: str) -> dict:
        return await self._post("set_group_name", {"group_id": group_id, "group_name": group_name})

    async def get_group_member_info(self, group_id: int, user_id: int, no_cache: bool = False) -> dict:
        return await self._post("get_group_member_info", {"group_id": group_id, "user_id": user_id, "no_cache": no_cache})

    async def get_group_member_list(self, group_id: int) -> dict:
        return await self._post("get_group_member_list", {"group_id": group_id})

    async def set_group_add_request(self, flag: str, sub_type: str, approve: bool, reason: str = "") -> dict:
        payload = {"flag": flag, "sub_type": sub_type, "approve": approve}
        if reason:
            payload["reason"] = reason
        return await self._post("set_group_add_request", payload)
