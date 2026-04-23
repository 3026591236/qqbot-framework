from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def _docker(*args: str) -> tuple[int, str, str]:
    if shutil.which("docker") is None:
        return 127, "", "docker not found"
    proc = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode("utf-8", errors="ignore"), err.decode("utf-8", errors="ignore")


async def get_onebot_status() -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.post(f"{settings.onebot_api_base.rstrip('/')}/get_status", json={})
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
    except Exception:
        logger.exception("napcat watchdog: get_status failed")
        return None


def is_online(status: dict[str, Any] | None) -> bool:
    if not isinstance(status, dict):
        return False
    data = status.get("data") if isinstance(status.get("data"), dict) else {}
    return bool(data.get("online"))


async def restart_napcat(reason: str = "offline") -> tuple[bool, str]:
    code, out, err = await _docker("restart", settings.napcat_container_name)
    ok = code == 0
    detail = (out or err or "").strip()
    if ok:
        logger.warning("napcat watchdog: restarted container=%s reason=%s", settings.napcat_container_name, reason)
    else:
        logger.error("napcat watchdog: restart failed container=%s reason=%s detail=%s", settings.napcat_container_name, reason, detail)
    return ok, detail


async def notify_owner(api, text: str) -> None:
    for owner_id in settings.owner_ids or []:
        try:
            await api.send_private_msg(int(owner_id), text)
        except Exception:
            logger.exception("napcat watchdog: notify owner failed owner_id=%s", owner_id)


async def napcat_watchdog_loop(api) -> None:
    if not settings.napcat_watchdog_enabled:
        logger.info("napcat watchdog disabled")
        return

    logger.info(
        "napcat watchdog started: interval=%ss restart_cooldown=%ss container=%s",
        settings.napcat_watchdog_interval_seconds,
        settings.napcat_watchdog_restart_cooldown_seconds,
        settings.napcat_container_name,
    )

    last_restart_at = 0.0
    while True:
        try:
            status = await get_onebot_status()
            online = is_online(status)
            if not online:
                now = asyncio.get_running_loop().time()
                if now - last_restart_at >= settings.napcat_watchdog_restart_cooldown_seconds:
                    ok, detail = await restart_napcat("onebot_offline")
                    last_restart_at = now
                    if settings.napcat_watchdog_notify_owner:
                        if ok:
                            await notify_owner(api, "NapCat 看门狗检测到 OneBot 离线，已自动重启容器。")
                        else:
                            await notify_owner(api, f"NapCat 看门狗检测到 OneBot 离线，但自动重启失败：{detail or '-'}")
                else:
                    logger.warning("napcat watchdog: offline detected but still in cooldown")
        except Exception:
            logger.exception("napcat watchdog loop failed")

        await asyncio.sleep(max(30, settings.napcat_watchdog_interval_seconds))
