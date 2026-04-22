from __future__ import annotations

from dataclasses import dataclass
import time

import httpx

from app.config import settings


@dataclass(frozen=True)
class MarketPlugin:
    name: str
    url: str
    version: str = "0.1.0"
    author: str = "unknown"
    description: str = ""
    sha256: str = ""  # optional integrity check


MARKET = {
    "example-hello": MarketPlugin(
        name="example-hello",
        version="1.0.0",
        author="OpenClaw",
        url="https://raw.githubusercontent.com/example/qqbot-plugins/main/example_hello.py",
        description="示例在线插件条目，需要替换成你自己的插件仓库地址",
    )
}


def normalize_market_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    # convenience: allow GitHub repo shorthand like "3026591236/qqbot-plugin-market"
    if url.count("/") == 1 and not url.startswith("http"):
        owner_repo = url
        return f"https://raw.githubusercontent.com/{owner_repo}/main/market.json"
    return url


def _remote_market() -> dict[str, MarketPlugin]:
    market_url = normalize_market_url(settings.market_url)
    if not market_url:
        return {}
    try:
        # GitHub raw has CDN caching; add a cache-busting query param to reduce stale market.json reads
        fetch_url = market_url
        sep = "&" if "?" in fetch_url else "?"
        fetch_url = f"{fetch_url}{sep}_ts={int(time.time())}"
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(fetch_url, headers={"Cache-Control": "no-cache"})
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
                sha256=item.get("sha256", ""),
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
