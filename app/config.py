from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # optional at import time
    def load_dotenv(*args, **kwargs):
        return False

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class Settings:
    app_name: str = os.getenv("QQBOT_APP_NAME", "QQ Bot Framework")
    host: str = os.getenv("QQBOT_HOST", "0.0.0.0")
    port: int = int(os.getenv("QQBOT_PORT", "9000"))
    debug: bool = os.getenv("QQBOT_DEBUG", "false").lower() == "true"
    adapter: str = os.getenv("QQBOT_ADAPTER", "onebot")
    onebot_api_base: str = os.getenv("ONEBOT_API_BASE", "http://127.0.0.1:5700")
    command_prefix: str = os.getenv("QQBOT_COMMAND_PREFIX", "/")
    log_level: str = os.getenv("QQBOT_LOG_LEVEL", "INFO")
    data_dir: str = os.getenv("QQBOT_DATA_DIR", str(BASE_DIR / "data"))
    sqlite_path: str = os.getenv("QQBOT_SQLITE_PATH", str(BASE_DIR / "data" / "qqbot.sqlite3"))
    owner_ids: list[str] = tuple(filter(None, os.getenv("QQBOT_OWNER_IDS", "").split(",")))
    market_url: str = os.getenv("QQBOT_MARKET_URL", "")
    public_base_url: str = os.getenv("QQBOT_PUBLIC_BASE_URL", "http://127.0.0.1:9000")
    card_mode: str = os.getenv("QQBOT_CARD_MODE", "text")
    auto_notify_group_invite: bool = os.getenv("QQBOT_AUTO_NOTIFY_GROUP_INVITE", "true").lower() == "true"
    lobster_enabled: bool = os.getenv("QQBOT_LOBSTER_ENABLED", "false").lower() == "true"
    lobster_webhook_url: str = os.getenv("QQBOT_LOBSTER_WEBHOOK_URL", "")
    lobster_webhook_secret: str = os.getenv("QQBOT_LOBSTER_WEBHOOK_SECRET", "")
    lobster_controller_id: str = os.getenv("QQBOT_LOBSTER_CONTROLLER_ID", "qqbot/lobster-bridge")
    lobster_runtime: str = os.getenv("QQBOT_LOBSTER_RUNTIME", "subagent")
    lobster_agent_id: str = os.getenv("QQBOT_LOBSTER_AGENT_ID", "")
    lobster_child_session_key: str = os.getenv("QQBOT_LOBSTER_CHILD_SESSION_KEY", "")
    lobster_notify_policy: str = os.getenv("QQBOT_LOBSTER_NOTIFY_POLICY", "done_only")
    panel_password: str = os.getenv("QQBOT_PANEL_PASSWORD", "")
    # Optional: restrict who can access /panel by client IP.
    # Example: "1.2.3.4,5.6.7.8" (empty means allow all)
    panel_allow_ips: tuple[str, ...] = tuple(filter(None, os.getenv("QQBOT_PANEL_ALLOW_IPS", "").split(",")))
    napcat_watchdog_enabled: bool = os.getenv("QQBOT_NAPCAT_WATCHDOG_ENABLED", "true").lower() == "true"
    napcat_watchdog_interval_seconds: int = int(os.getenv("QQBOT_NAPCAT_WATCHDOG_INTERVAL_SECONDS", "120"))
    napcat_watchdog_restart_cooldown_seconds: int = int(os.getenv("QQBOT_NAPCAT_WATCHDOG_RESTART_COOLDOWN_SECONDS", "900"))
    napcat_watchdog_notify_owner: bool = os.getenv("QQBOT_NAPCAT_WATCHDOG_NOTIFY_OWNER", "true").lower() == "true"
    napcat_container_name: str = os.getenv("QQBOT_NAPCAT_CONTAINER_NAME", "napcat")


settings = Settings()
