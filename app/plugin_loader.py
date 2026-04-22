from __future__ import annotations

import importlib
import logging
import pkgutil
from types import ModuleType
from typing import Iterable
import inspect

from app.plugin_registry import is_enabled, set_plugin_info

logger = logging.getLogger(__name__)


def _module_plugins(module: ModuleType) -> list[object]:
    result = []
    direct = getattr(module, "plugin", None)
    if direct is not None and not inspect.isclass(direct):
        result.append(direct)
    for value in module.__dict__.values():
        if value is None:
            continue
        if inspect.isclass(value):
            continue
        if hasattr(value, "dispatch") and hasattr(value, "name") and value not in result:
            result.append(value)
    return result


def discover_plugins(package_name: str = "app.plugins") -> Iterable[object]:
    package = importlib.import_module(package_name)
    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        module: ModuleType = importlib.import_module(module_info.name)
        for plugin in _module_plugins(module):
            plugin_name = getattr(plugin, "name", module_info.name.rsplit(".", 1)[-1])
            if not is_enabled(plugin_name):
                logger.info("plugin disabled: %s", plugin_name)
                continue
            meta = getattr(plugin, "meta", None)
            if meta is not None:
                plugin_type = plugin.__class__.__name__.replace("Plugin", "").lower() or "unknown"
                trigger = ""
                if hasattr(plugin, "command"):
                    trigger = getattr(plugin, "command", "") or ""
                elif hasattr(plugin, "keyword"):
                    trigger = getattr(plugin, "keyword", "") or ""
                elif hasattr(plugin, "pattern"):
                    trigger = getattr(plugin, "pattern", "") or ""
                set_plugin_info(
                    plugin_name,
                    enabled=True,
                    version=getattr(meta, "version", "0.1.0"),
                    author=getattr(meta, "author", "unknown"),
                    description=getattr(meta, "description", ""),
                    dependencies=getattr(meta, "dependencies", []),
                    package=package_name,
                    module=module_info.name.rsplit(".", 1)[-1],
                    source=(module.__file__ or ""),
                    plugin_type=plugin_type,
                    trigger=trigger,
                )
            yield plugin


def discover_all_plugins() -> Iterable[object]:
    for package_name in ("app.plugins", "user_plugins"):
        try:
            yield from discover_plugins(package_name)
        except ModuleNotFoundError:
            logger.warning("plugin package not found: %s", package_name)
