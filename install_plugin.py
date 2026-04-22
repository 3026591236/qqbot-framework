#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from app.plugin_installer import install_plugin, uninstall_plugin
from app.plugin_market import get_market_plugin, list_market_plugins
from app.plugin_registry import get_plugin_info, list_plugins, set_enabled

USAGE = """Usage:
  python3 install_plugin.py install /path/to/plugin.py|plugin_dir|plugin.zip|https://...|market:name
  python3 install_plugin.py upgrade <plugin_name>
  python3 install_plugin.py uninstall <plugin_name>
  python3 install_plugin.py enable <plugin_name>
  python3 install_plugin.py disable <plugin_name>
  python3 install_plugin.py list
  python3 install_plugin.py market
"""


def main() -> int:
    if len(sys.argv) < 2:
        print(USAGE)
        return 2

    cmd = sys.argv[1]
    target = Path(__file__).resolve().parent / "user_plugins"

    if cmd == "install":
        if len(sys.argv) != 3:
            print(USAGE)
            return 2
        source = sys.argv[2]
        if source.startswith("market:"):
            name = source.split(":", 1)[1]
            item = get_market_plugin(name)
            if item is None:
                print(f"Market plugin not found: {name}")
                return 1
            source = item.url
        installed = install_plugin(source, target)
        print(f"Installed plugin to: {installed}")
        print("Restart the bot service to load the new plugin.")
        return 0

    if cmd == "upgrade" and len(sys.argv) == 3:
        name = sys.argv[2]
        info = get_plugin_info(name)
        source = info.get("source")
        if not source:
            item = get_market_plugin(name)
            if item is None:
                print(f"No upgrade source found for: {name}")
                return 1
            source = item.url
        installed = install_plugin(source, target)
        print(f"Upgraded plugin to: {installed}")
        print("Restart the bot service to load the new plugin.")
        return 0

    if cmd == "uninstall" and len(sys.argv) == 3:
        name = sys.argv[2]
        ok = uninstall_plugin(name, target)
        if ok:
            print(f"Uninstalled plugin: {name}")
            return 0
        print(f"Plugin not found: {name}")
        return 1

    if cmd == "enable" and len(sys.argv) == 3:
        set_enabled(sys.argv[2], True)
        print(f"Enabled plugin: {sys.argv[2]}")
        return 0

    if cmd == "disable" and len(sys.argv) == 3:
        set_enabled(sys.argv[2], False)
        print(f"Disabled plugin: {sys.argv[2]}")
        return 0

    if cmd == "list":
        for name, info in list_plugins().items():
            print(f"{name}\tenabled={info.get('enabled', True)}\tversion={info.get('version', '-')}\tauthor={info.get('author', '-')}\tsource={info.get('source', '-')}")
        return 0

    if cmd == "market":
        for item in list_market_plugins():
            print(f"{item.name}\t{item.version}\t{item.author}\t{item.url}\t{item.description}")
        return 0

    print(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
