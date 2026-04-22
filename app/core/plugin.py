from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


def _matches_command(text: str, command: str) -> bool:
    text = (text or "").strip()
    command = (command or "").strip()
    if not text or not command:
        return False

    variants = {command}
    if command.startswith("/"):
        variants.add(command[1:])
    else:
        variants.add(f"/{command}")

    for variant in variants:
        if not variant:
            continue
        if text == variant or text.startswith(variant + " "):
            return True
    return False

Handler = Callable[["MessageContext"], Awaitable[None]]


@dataclass
class PluginMeta:
    name: str
    version: str = "0.1.0"
    author: str = "unknown"
    description: str = ""
    dependencies: list[str] = field(default_factory=list)


@dataclass
class CommandPlugin:
    name: str
    command: str
    description: str = ""
    meta: PluginMeta | None = None
    _handler: Optional[Handler] = None

    def __post_init__(self) -> None:
        if self.meta is None:
            self.meta = PluginMeta(name=self.name, description=self.description)

    def handle(self, func: Handler) -> Handler:
        self._handler = func
        return func

    async def dispatch(self, ctx: "MessageContext") -> bool:
        if not _matches_command(ctx.text, self.command):
            return False
        if self._handler is None:
            return False
        await self._handler(ctx)
        return True


@dataclass
class KeywordPlugin:
    name: str
    keyword: str
    description: str = ""
    meta: PluginMeta | None = None
    _handler: Optional[Handler] = None

    def __post_init__(self) -> None:
        if self.meta is None:
            self.meta = PluginMeta(name=self.name, description=self.description)

    def handle(self, func: Handler) -> Handler:
        self._handler = func
        return func

    async def dispatch(self, ctx: "MessageContext") -> bool:
        if self.keyword not in ctx.text:
            return False
        if self._handler is None:
            return False
        await self._handler(ctx)
        return True


@dataclass
class RegexPlugin:
    name: str
    pattern: str
    description: str = ""
    meta: PluginMeta | None = None
    _handler: Optional[Handler] = None

    def __post_init__(self) -> None:
        if self.meta is None:
            self.meta = PluginMeta(name=self.name, description=self.description)

    def handle(self, func: Handler) -> Handler:
        self._handler = func
        return func

    async def dispatch(self, ctx: "MessageContext") -> bool:
        import re

        if not re.search(self.pattern, ctx.text):
            return False
        if self._handler is None:
            return False
        await self._handler(ctx)
        return True
