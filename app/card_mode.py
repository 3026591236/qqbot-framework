from __future__ import annotations

import os
import time
from pathlib import Path

from app.config import settings
from app.db import get_conn
from app.renderers.card_image import (
    DEFAULT_MAX_CARD_HEIGHT,
    list_card_styles,
    paginate_info_card_lines,
    render_info_card,
)

CARD_STYLE_KEY = "QQBOT_CARD_STYLE"
DEFAULT_CARD_STYLE = os.getenv(CARD_STYLE_KEY, "light").strip().lower() or "light"


def normalize_card_style(value: str | None) -> str:
    v = (value or "").strip().lower()
    mapping = {
        # internal keys
        "light": "light",
        "dark": "dark",
        "compact": "compact",
        "minimal": "minimal",
        "sakura": "sakura",
        "mint": "mint",
        "paper": "paper",
        "blackgold": "blackgold",
        # chinese aliases
        "浅色": "light",
        "默认": "light",
        "经典": "light",
        "深色": "dark",
        "夜间": "dark",
        "夜蓝": "dark",
        "紧凑": "compact",
        "密集": "compact",
        "极简": "minimal",
        "简洁": "minimal",
        "樱粉": "sakura",
        "粉": "sakura",
        "薄荷": "mint",
        "清爽": "mint",
        "纸质": "paper",
        "暖黄": "paper",
        "黑金": "blackgold",
        "高级": "blackgold",
    }
    return mapping.get(v, v or "light")


def get_card_style_label(style: str | None = None) -> str:
    key = normalize_card_style(style or os.getenv(CARD_STYLE_KEY, DEFAULT_CARD_STYLE))
    for item in list_card_styles():
        if item.get("key") == key:
            return f"{item.get('label')}（{key}）"
    return f"{key}"


def list_card_style_choices() -> str:
    items = list_card_styles()
    return " / ".join(f"{x['label']}({x['key']})" for x in items)

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
CARD_MODE_KEY = "QQBOT_CARD_MODE"
DEFAULT_CARD_MODE = os.getenv(CARD_MODE_KEY, "text").strip().lower() or "text"


def normalize_card_mode(value: str) -> str:
    value = (value or "").strip().lower()
    mapping = {
        "文字": "text",
        "文本": "text",
        "text": "text",
        "txt": "text",
        "图片": "image",
        "图": "image",
        "image": "image",
        "img": "image",
    }
    return mapping.get(value, value)


def _ensure_group_card_mode_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_card_mode_settings (
                group_id INTEGER PRIMARY KEY,
                card_mode TEXT NOT NULL DEFAULT 'text',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )


def get_card_mode(group_id: int | None = None) -> str:
    if group_id:
        _ensure_group_card_mode_table()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT card_mode FROM group_card_mode_settings WHERE group_id=?",
                (int(group_id),),
            ).fetchone()
            if row is not None:
                mode = normalize_card_mode(row["card_mode"])
                if mode in {"text", "image"}:
                    return mode
    mode = normalize_card_mode(os.getenv(CARD_MODE_KEY, DEFAULT_CARD_MODE))
    return mode if mode in {"text", "image"} else "text"


def get_card_mode_label(group_id: int | None = None) -> str:
    return "图片卡片" if get_card_mode(group_id) == "image" else "文字卡片"


def _save_env_value(key: str, value: str) -> None:
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def set_card_mode(mode: str) -> str:
    mode = normalize_card_mode(mode)
    if mode not in {"text", "image"}:
        raise ValueError("卡片模式只能是 text/image 或 文字/图片")
    os.environ[CARD_MODE_KEY] = mode
    _save_env_value(CARD_MODE_KEY, mode)
    return mode


def set_group_card_mode(group_id: int, mode: str) -> str:
    mode = normalize_card_mode(mode)
    if mode not in {"text", "image"}:
        raise ValueError("卡片模式只能是 text/image 或 文字/图片")
    _ensure_group_card_mode_table()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO group_card_mode_settings (group_id, card_mode, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(group_id) DO UPDATE SET card_mode=excluded.card_mode, updated_at=excluded.updated_at",
            (int(group_id), mode),
        )
    return mode


def build_text_card(title: str, lines: list[str], footer: str = "") -> str:
    body = "\n".join(f"┃ {line}" for line in lines if line.strip())
    text = f"┏━━━〔 {title} 〕━━━\n{body}"
    if footer.strip():
        text += f"\n┣━━━━━━━━━━━━\n┃ {footer.strip()}"
    text += "\n┗━━━━━━━━━━━━"
    return text


def build_image_url(filename: str) -> str:
    return settings.public_base_url.rstrip("/") + "/static/cards/" + filename


def render_text_to_card_images(message: str, title: str = "QQ机器人消息", style: str | None = None) -> list[str]:
    cards_dir = Path(settings.data_dir) / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)

    text = (message or "").replace("\r\n", "\n").strip()
    raw_lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not raw_lines:
        raw_lines = ["（空消息）"]

    style_key = normalize_card_style(style or os.getenv(CARD_STYLE_KEY, DEFAULT_CARD_STYLE))

    subtitle = f"图片卡片风格：{get_card_style_label(style_key)}"
    body = raw_lines
    if len(raw_lines) >= 2 and len(raw_lines[0]) <= 22:
        title = raw_lines[0]
        body = raw_lines[1:] or ["（无详细内容）"]

    page_groups = paginate_info_card_lines(
        title=title,
        subtitle=subtitle,
        lines=body,
        footer_builder=lambda index, total: "图片卡片" if total <= 1 else f"图片卡片 · 第 {index + 1}/{total} 页",
        max_height=DEFAULT_MAX_CARD_HEIGHT,
        style=style_key,
    )

    pages: list[str] = []
    total = len(page_groups)
    for index, chunk in enumerate(page_groups):
        output = cards_dir / f"global_{ts}_{index + 1}.png"
        footer = "图片卡片" if total <= 1 else f"图片卡片 · 第 {index + 1}/{total} 页"
        path = render_info_card(
            title=title,
            subtitle=subtitle,
            lines=chunk,
            footer=footer,
            output_path=str(output),
            style=style_key,
        )
        pages.append(build_image_url(Path(path).name))
    return pages
