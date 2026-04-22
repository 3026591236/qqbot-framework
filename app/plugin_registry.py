from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


def _registry_path() -> Path:
    return Path(settings.data_dir) / "plugins.json"


def load_registry() -> dict[str, Any]:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {"plugins": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(data: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_enabled(plugin_name: str) -> bool:
    data = load_registry()
    plugins = data.get("plugins", {})
    info = plugins.get(plugin_name, {})
    return info.get("enabled", True)


def set_enabled(plugin_name: str, enabled: bool) -> None:
    data = load_registry()
    plugins = data.setdefault("plugins", {})
    info = plugins.setdefault(plugin_name, {})
    info["enabled"] = enabled
    save_registry(data)


def set_plugin_info(plugin_name: str, **kwargs: Any) -> None:
    data = load_registry()
    plugins = data.setdefault("plugins", {})
    info = plugins.setdefault(plugin_name, {})
    info.update(kwargs)
    save_registry(data)


def get_plugin_info(plugin_name: str) -> dict[str, Any]:
    return load_registry().get("plugins", {}).get(plugin_name, {})


def remove_plugin_info(plugin_name: str) -> None:
    data = load_registry()
    plugins = data.setdefault("plugins", {})
    plugins.pop(plugin_name, None)
    save_registry(data)


def list_plugins() -> dict[str, Any]:
    return load_registry().get("plugins", {})
