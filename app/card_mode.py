from __future__ import annotations

import os
import time
from pathlib import Path

from app.config import settings
from app.renderers.card_image import render_info_card

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


def get_card_mode() -> str:
    mode = normalize_card_mode(os.getenv(CARD_MODE_KEY, DEFAULT_CARD_MODE))
    return mode if mode in {"text", "image"} else "text"


def get_card_mode_label() -> str:
    return "图片卡片" if get_card_mode() == "image" else "文字卡片"


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


def build_text_card(title: str, lines: list[str], footer: str = "") -> str:
    body = "\n".join(f"┃ {line}" for line in lines if line.strip())
    text = f"┏━━━〔 {title} 〕━━━\n{body}"
    if footer.strip():
        text += f"\n┣━━━━━━━━━━━━\n┃ {footer.strip()}"
    text += "\n┗━━━━━━━━━━━━"
    return text


def build_image_url(filename: str) -> str:
    return settings.public_base_url.rstrip("/") + "/static/cards/" + filename


def render_text_to_card_images(message: str, title: str = "QQ机器人消息") -> list[str]:
    cards_dir = Path(settings.data_dir) / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)

    text = (message or "").replace("\r\n", "\n").strip()
    raw_lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not raw_lines:
        raw_lines = ["（空消息）"]

    subtitle = "全局图片卡片模式"
    body = raw_lines
    if len(raw_lines) >= 2 and len(raw_lines[0]) <= 22:
        title = raw_lines[0]
        body = raw_lines[1:] or ["（无详细内容）"]

    page_size = 10
    pages: list[str] = []
    total = max(1, (len(body) + page_size - 1) // page_size)
    for index in range(total):
        chunk = body[index * page_size:(index + 1) * page_size]
        output = cards_dir / f"global_{ts}_{index + 1}.png"
        footer = f"当前为全局图片卡片模式 · 第 {index + 1}/{total} 页"
        path = render_info_card(
            title=title,
            subtitle=subtitle,
            lines=chunk,
            footer=footer,
            output_path=str(output),
        )
        pages.append(build_image_url(Path(path).name))
    return pages
