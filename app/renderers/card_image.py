from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

# NOTE:
# These styles only affect bot-rendered image cards (PIL generated images).
# They do NOT affect any platform-native cards (json/xml/etc).

DEFAULT_CARD_WIDTH = 1000
DEFAULT_MAX_CARD_HEIGHT = 2400

logger = logging.getLogger(__name__)


CARD_STYLES: dict[str, dict] = {
    # Default (existing) light style
    "light": {
        "label": "浅色 · 蓝紫",
        "card_bg": "#f3f6fb",
        "panel_bg": "#ffffff",
        "title": "#111827",
        "text": "#374151",
        "muted": "#6b7280",
        "accent": "#4f46e5",
        "border": "#dbe3f0",
        "radius": 30,
        "outer": 28,
        "inner": 36,
        "line_spacing": 16,
        "title_size": 38,
        "subtitle_size": 22,
        "text_size": 28,
        "footer_size": 22,
        "accent_bar": True,
        "bullet": "• ",
        "indent": "  ",
    },
    # Dark mode
    "dark": {
        "label": "深色 · 夜蓝",
        "card_bg": "#0b1020",
        "panel_bg": "#0f172a",
        "title": "#e5e7eb",
        "text": "#cbd5e1",
        "muted": "#94a3b8",
        "accent": "#60a5fa",
        "border": "#1f2a44",
        "radius": 30,
        "outer": 28,
        "inner": 36,
        "line_spacing": 16,
        "title_size": 38,
        "subtitle_size": 22,
        "text_size": 28,
        "footer_size": 22,
        "accent_bar": True,
        "bullet": "• ",
        "indent": "  ",
    },
    # Compact: more content per page
    "compact": {
        "label": "紧凑 · 信息密度",
        "card_bg": "#f8fafc",
        "panel_bg": "#ffffff",
        "title": "#0f172a",
        "text": "#334155",
        "muted": "#64748b",
        "accent": "#10b981",
        "border": "#e2e8f0",
        "radius": 22,
        "outer": 20,
        "inner": 26,
        "line_spacing": 10,
        "title_size": 34,
        "subtitle_size": 20,
        "text_size": 24,
        "footer_size": 20,
        "accent_bar": False,
        "bullet": "- ",
        "indent": "  ",
    },
    # Minimal: clean, no accent bar
    "minimal": {
        "label": "极简 · 白纸",
        "card_bg": "#ffffff",
        "panel_bg": "#ffffff",
        "title": "#111827",
        "text": "#374151",
        "muted": "#6b7280",
        "accent": "#111827",
        "border": "#e5e7eb",
        "radius": 18,
        "outer": 18,
        "inner": 26,
        "line_spacing": 12,
        "title_size": 36,
        "subtitle_size": 20,
        "text_size": 26,
        "footer_size": 20,
        "accent_bar": False,
        "bullet": "• ",
        "indent": "  ",
    },
    # New: Sakura
    "sakura": {
        "label": "樱粉 · 柔和",
        "card_bg": "#fff1f2",
        "panel_bg": "#ffffff",
        "title": "#111827",
        "text": "#374151",
        "muted": "#9f1239",
        "accent": "#ec4899",
        "border": "#fecdd3",
        "radius": 28,
        "outer": 26,
        "inner": 34,
        "line_spacing": 14,
        "title_size": 38,
        "subtitle_size": 22,
        "text_size": 28,
        "footer_size": 22,
        "accent_bar": True,
        "bullet": "• ",
        "indent": "  ",
    },
    # New: Mint
    "mint": {
        "label": "薄荷 · 清爽",
        "card_bg": "#ecfdf5",
        "panel_bg": "#ffffff",
        "title": "#064e3b",
        "text": "#065f46",
        "muted": "#0f766e",
        "accent": "#10b981",
        "border": "#a7f3d0",
        "radius": 28,
        "outer": 26,
        "inner": 34,
        "line_spacing": 14,
        "title_size": 38,
        "subtitle_size": 22,
        "text_size": 28,
        "footer_size": 22,
        "accent_bar": True,
        "bullet": "• ",
        "indent": "  ",
    },
    # New: Amber paper
    "paper": {
        "label": "纸质 · 暖黄",
        "card_bg": "#fffbeb",
        "panel_bg": "#fffdf7",
        "title": "#3f2d1c",
        "text": "#4b3a2a",
        "muted": "#8a6a4a",
        "accent": "#f59e0b",
        "border": "#fde68a",
        "radius": 24,
        "outer": 24,
        "inner": 32,
        "line_spacing": 14,
        "title_size": 38,
        "subtitle_size": 22,
        "text_size": 28,
        "footer_size": 22,
        "accent_bar": False,
        "bullet": "• ",
        "indent": "  ",
    },
    # New: Black + Gold
    "blackgold": {
        "label": "黑金 · 高级",
        "card_bg": "#070a12",
        "panel_bg": "#0b1224",
        "title": "#f8fafc",
        "text": "#e2e8f0",
        "muted": "#cbd5e1",
        "accent": "#fbbf24",
        "border": "#1f2a44",
        "radius": 30,
        "outer": 28,
        "inner": 36,
        "line_spacing": 16,
        "title_size": 38,
        "subtitle_size": 22,
        "text_size": 28,
        "footer_size": 22,
        "accent_bar": True,
        "bullet": "• ",
        "indent": "  ",
    },
}


def list_card_styles() -> list[dict]:
    result: list[dict] = []
    for key, theme in CARD_STYLES.items():
        result.append({"key": key, "label": str(theme.get("label") or key)})
    return result


def get_card_style(style: str | None) -> dict:
    key = (style or "").strip().lower() or "light"
    return CARD_STYLES.get(key, CARD_STYLES["light"])


def _load_font(size: int, bold: bool = False):
    candidates = []
    if bold:
        candidates.extend(
            [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/arphic/ukai.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/arphic/ukai.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
    for path in candidates:
        try:
            font = ImageFont.truetype(path, size)
            logger.info("card_image font selected: %s", path)
            return font
        except Exception:
            continue
    logger.warning("card_image fallback font used; CJK text may render incorrectly")
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]

    result: list[str] = []
    for raw in text.splitlines() or [text]:
        raw = raw.strip()
        if not raw:
            result.append("")
            continue

        current = ""
        for ch in raw:
            candidate = current + ch
            bbox = draw.textbbox((0, 0), candidate, font=font)
            width = bbox[2] - bbox[0]
            if current and width > max_width:
                result.append(current)
                current = ch
            else:
                current = candidate
        if current:
            result.append(current)
    return result or [""]


def _line_height(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text or " ", font=font)
    return max(bbox[3] - bbox[1], 0)


def _measure_multiline(draw: ImageDraw.ImageDraw, lines: list[str], font, spacing: int) -> int:
    height = 0
    for line in lines:
        height += _line_height(draw, line, font) + spacing
    return max(height - spacing, 0)


def _build_card_layout(
    *,
    title: str,
    subtitle: str = "",
    lines: Iterable[str],
    footer: str = "",
    width: int = DEFAULT_CARD_WIDTH,
    style: str = "light",
) -> dict:
    theme = get_card_style(style)

    items = [str(x).strip() for x in lines if str(x).strip()]
    title_font = _load_font(int(theme["title_size"]), bold=True)
    subtitle_font = _load_font(int(theme["subtitle_size"]))
    text_font = _load_font(int(theme["text_size"]))
    footer_font = _load_font(int(theme["footer_size"]))

    outer = int(theme["outer"])
    inner = int(theme["inner"])
    line_spacing = int(theme["line_spacing"])

    temp = Image.new("RGB", (width, 1200), theme["card_bg"])
    draw = ImageDraw.Draw(temp)

    content_max_width = width - (outer + 56) - (outer + inner)
    wrapped_title = _wrap_text(draw, title, title_font, content_max_width)
    wrapped_subtitle = _wrap_text(draw, subtitle, subtitle_font, content_max_width) if subtitle else []

    bullet = str(theme.get("bullet", "• "))
    indent = str(theme.get("indent", "  "))

    wrapped_body: list[str] = []
    for item in items:
        wrapped = _wrap_text(draw, item, text_font, content_max_width - 40)
        if wrapped:
            wrapped_body.append(f"{bullet}{wrapped[0]}")
            wrapped_body.extend(f"{indent}{line}" for line in wrapped[1:])
        else:
            wrapped_body.append(bullet.strip() or "•")

    wrapped_footer = _wrap_text(draw, footer, footer_font, content_max_width) if footer else []

    title_h = _measure_multiline(draw, wrapped_title, title_font, 10)
    subtitle_h = _measure_multiline(draw, wrapped_subtitle, subtitle_font, 8) if subtitle else 0
    body_h = _measure_multiline(draw, wrapped_body, text_font, line_spacing)
    footer_h = _measure_multiline(draw, wrapped_footer, footer_font, 8) if footer else 0

    panel_h = inner + title_h + 12
    if subtitle:
        panel_h += subtitle_h + 18
    panel_h += 18 + body_h
    if footer:
        panel_h += 28 + footer_h
    panel_h += inner

    height = panel_h + outer * 2
    return {
        "theme": theme,
        "style": style,
        "items": items,
        "title_font": title_font,
        "subtitle_font": subtitle_font,
        "text_font": text_font,
        "footer_font": footer_font,
        "width": width,
        "height": height,
        "outer": outer,
        "inner": inner,
        "line_spacing": line_spacing,
        "wrapped_title": wrapped_title,
        "wrapped_subtitle": wrapped_subtitle,
        "wrapped_body": wrapped_body,
        "wrapped_footer": wrapped_footer,
    }


def estimate_info_card_height(
    *,
    title: str,
    subtitle: str = "",
    lines: Iterable[str],
    footer: str = "",
    width: int = DEFAULT_CARD_WIDTH,
    style: str = "light",
) -> int:
    return int(
        _build_card_layout(title=title, subtitle=subtitle, lines=lines, footer=footer, width=width, style=style)[
            "height"
        ]
    )


def paginate_info_card_lines(
    *,
    title: str,
    subtitle: str = "",
    lines: Iterable[str],
    footer_builder=None,
    max_height: int = DEFAULT_MAX_CARD_HEIGHT,
    width: int = DEFAULT_CARD_WIDTH,
    style: str = "light",
) -> list[list[str]]:
    items = [str(x).strip() for x in lines if str(x).strip()]
    if not items:
        return [["（空消息）"]]

    if footer_builder is None:
        footer_builder = lambda index, total: ""

    if (
        estimate_info_card_height(
            title=title,
            subtitle=subtitle,
            lines=items,
            footer=footer_builder(0, 1),
            width=width,
            style=style,
        )
        <= max_height
    ):
        return [items]

    pages: list[list[str]] = []
    current: list[str] = []
    for item in items:
        candidate = current + [item]
        footer = footer_builder(len(pages), len(pages) + 1)
        if current and (
            estimate_info_card_height(
                title=title,
                subtitle=subtitle,
                lines=candidate,
                footer=footer,
                width=width,
                style=style,
            )
            > max_height
        ):
            pages.append(current)
            current = [item]
        else:
            current = candidate

    if current:
        pages.append(current)

    return pages or [["（空消息）"]]


def render_info_card(
    *,
    title: str,
    subtitle: str = "",
    lines: Iterable[str],
    footer: str = "",
    output_path: str,
    style: str = "light",
) -> str:
    layout = _build_card_layout(title=title, subtitle=subtitle, lines=lines, footer=footer, style=style)

    theme = layout["theme"]

    width = layout["width"]
    height = layout["height"]
    outer = layout["outer"]
    inner = layout["inner"]
    line_spacing = layout["line_spacing"]
    title_font = layout["title_font"]
    subtitle_font = layout["subtitle_font"]
    text_font = layout["text_font"]
    footer_font = layout["footer_font"]
    wrapped_title = layout["wrapped_title"]
    wrapped_subtitle = layout["wrapped_subtitle"]
    wrapped_body = layout["wrapped_body"]
    wrapped_footer = layout["wrapped_footer"]

    img = Image.new("RGB", (width, height), theme["card_bg"])
    draw = ImageDraw.Draw(img)

    radius = int(theme.get("radius", 30))
    draw.rounded_rectangle(
        (outer, outer, width - outer, height - outer),
        radius=radius,
        fill=theme["panel_bg"],
        outline=theme["border"],
        width=2,
    )
    if bool(theme.get("accent_bar", True)):
        draw.rounded_rectangle(
            (outer + 24, outer + 24, outer + 24 + 10, height - outer - 24),
            radius=5,
            fill=theme["accent"],
        )

    x = outer + 56
    y = outer + inner
    for line in wrapped_title:
        draw.text((x, y), line, fill=theme["title"], font=title_font)
        y += _line_height(draw, line, title_font) + 10
    y += 2

    if subtitle:
        for line in wrapped_subtitle:
            draw.text((x, y), line, fill=theme["muted"], font=subtitle_font)
            y += _line_height(draw, line, subtitle_font) + 8
        y += 10

    draw.line((x, y, width - outer - inner, y), fill=theme["border"], width=2)
    y += 24

    for line in wrapped_body:
        draw.text((x, y), line, fill=theme["text"], font=text_font)
        y += _line_height(draw, line, text_font) + line_spacing

    if footer:
        y += 10
        draw.line((x, y, width - outer - inner, y), fill=theme["border"], width=2)
        y += 18
        for line in wrapped_footer:
            draw.text((x, y), line, fill=theme["muted"], font=footer_font)
            y += _line_height(draw, line, footer_font) + 8

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG")
    return str(out)
