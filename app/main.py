from __future__ import annotations

import logging

import asyncio

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.bot import BotApp
from app.db import init_db
from app.logging_setup import setup_logging
from app.plugin_loader import discover_all_plugins
from app.web.panel import router as panel_router

try:
    from user_plugins.update_checker import auto_update_notifier
except Exception:  # optional plugin hook
    auto_update_notifier = None

try:
    from user_plugins.cdk_rewards import process_random_speaker_tick
except Exception:  # optional plugin hook
    process_random_speaker_tick = None

try:
    from app.napcat_watchdog import napcat_watchdog_loop
except Exception:  # optional watchdog hook
    napcat_watchdog_loop = None

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=settings.data_dir), name="static")
app.include_router(panel_router)
bot = BotApp(api_base=settings.onebot_api_base, adapter_name=settings.adapter)

for plugin in discover_all_plugins():
    bot.register_plugin(plugin)
    logger.info("loaded plugin: %s", getattr(plugin, "name", plugin.__class__.__name__))


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    logger.info("database initialized: %s", settings.sqlite_path)
    if auto_update_notifier is not None:
        asyncio.create_task(auto_update_notifier(bot.api))
        logger.info("auto update notifier started")

    if process_random_speaker_tick is not None:
        async def _random_speaker_loop() -> None:
            while True:
                try:
                    await process_random_speaker_tick(bot.api)
                except Exception:
                    logger.exception("random speaker tick failed")
                await asyncio.sleep(60)

        asyncio.create_task(_random_speaker_loop())
        logger.info("random speaker tick loop started")

    if napcat_watchdog_loop is not None:
        asyncio.create_task(napcat_watchdog_loop(bot.api))
        logger.info("napcat watchdog loop started")


@app.get("/")
async def index() -> dict:
    return {
        "ok": True,
        "service": "qqbot-framework",
        "app_name": settings.app_name,
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/onebot/event")
async def onebot_event(request: Request) -> dict:
    payload = await request.json()
    handled = await bot.handle_event(payload)
    return {"ok": True, "handled": handled}
