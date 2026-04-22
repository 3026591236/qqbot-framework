from __future__ import annotations

import logging
from typing import Iterable

from app.core.plugin import CommandPlugin, KeywordPlugin, RegexPlugin
from app.core.context import MessageContext

Plugin = CommandPlugin | KeywordPlugin | RegexPlugin

logger = logging.getLogger(__name__)


class Router:
    def __init__(self) -> None:
        self._plugins: list[Plugin] = []

    def register(self, plugin: Plugin) -> None:
        self._plugins.append(plugin)

    def register_many(self, plugins: Iterable[Plugin]) -> None:
        for plugin in plugins:
            self.register(plugin)

    async def dispatch(self, ctx: MessageContext) -> bool:
        for plugin in self._plugins:
            plugin_name = getattr(plugin, "name", plugin.__class__.__name__)
            try:
                handled = await plugin.dispatch(ctx)
            except Exception:
                logger.exception(
                    "plugin dispatch failed: plugin=%s user_id=%s group_id=%s message_type=%s text=%r",
                    plugin_name,
                    ctx.user_id,
                    ctx.group_id,
                    ctx.message_type,
                    ctx.text,
                )
                continue
            if handled:
                logger.info(
                    "plugin handled message: plugin=%s user_id=%s group_id=%s message_type=%s text=%r",
                    plugin_name,
                    ctx.user_id,
                    ctx.group_id,
                    ctx.message_type,
                    ctx.text,
                )
                return True
        return False
