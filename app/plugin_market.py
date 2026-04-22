from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass(frozen=True)
class MarketPlugin:
    name: str
    url: str
    version: str = "0.1.0"
    author: str = "unknown"
    description: str = ""


MARKET = {
    "example-hello": MarketPlugin(
        name="example-hello",
        version="1.0.0",
        author="OpenClaw",
        url="https://raw.githubusercontent.com/example/qqbot-plugins/main/example_hello.py",
        description="示例在线插件条目，需要替换成你自己的插件仓库地址",
    )
}


def _remote_market() -> dict[str, MarketPlugin]:
    if not settings.market_url:
        return {}
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(settings.market_url)
            resp.raise_for_status()
            payload = resp.json()
        result = {}
        for item in payload.get("plugins", []):
            plugin = MarketPlugin(
                name=item["name"],
                url=item["url"],
                version=item.get("version", "0.1.0"),
                author=item.get("author", "unknown"),
                description=item.get("description", ""),
            )
            result[plugin.name] = plugin
        return result
    except Exception:
        return {}


def merged_market() -> dict[str, MarketPlugin]:
    data = dict(MARKET)
    data.update(_remote_market())
    return data


def get_market_plugin(name: str) -> MarketPlugin | None:
    return merged_market().get(name)


def list_market_plugins() -> list[MarketPlugin]:
    return list(merged_market().values())
