from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

CARD_BG = "#f3f6fb"
PANEL_BG = "#ffffff"
TITLE_COLOR = "#111827"
TEXT_COLOR = "#374151"
MUTED_COLOR = "#6b7280"
ACCENT = "#4f46e5"
BORDER = "#dbe3f0"
logger = logging.getLogger(__name__)


def _load_font(size: int, bold: bool = False):
    candidates = []
    if bold:
        candidates.extend([
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/arphic/ukai.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/arphic/ukai.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ])
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


def _measure_multiline(draw: ImageDraw.ImageDraw, lines: list[str], font, spacing: int) -> int:
    height = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line or " ", font=font)
        height += (bbox[3] - bbox[1]) + spacing
    return max(height - spacing, 0)


def render_info_card(
    *,
    title: str,
    subtitle: str = "",
    lines: Iterable[str],
    footer: str = "",
    output_path: str,
) -> str:
    items = [str(x).strip() for x in lines if str(x).strip()]
    title_font = _load_font(38, bold=True)
    subtitle_font = _load_font(22)
    text_font = _load_font(28)
    footer_font = _load_font(22)

    width = 1000
    outer = 28
    inner = 36
    line_spacing = 16

    temp = Image.new("RGB", (width, 1200), CARD_BG)
    draw = ImageDraw.Draw(temp)

    content_max_width = width - (outer + 56) - (outer + inner)
    wrapped_title = _wrap_text(draw, title, title_font, content_max_width)
    wrapped_subtitle = _wrap_text(draw, subtitle, subtitle_font, content_max_width) if subtitle else []
    wrapped_body: list[str] = []
    for item in items:
        wrapped = _wrap_text(draw, item, text_font, content_max_width - 40)
        if wrapped:
            wrapped_body.append(f"• {wrapped[0]}")
            wrapped_body.extend(f"  {line}" for line in wrapped[1:])
        else:
            wrapped_body.append("•")
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
    img = Image.new("RGB", (width, height), CARD_BG)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((outer, outer, width - outer, height - outer), radius=30, fill=PANEL_BG, outline=BORDER, width=2)
    draw.rounded_rectangle((outer + 24, outer + 24, outer + 24 + 10, height - outer - 24), radius=5, fill=ACCENT)

    x = outer + 56
    y = outer + inner
    for line in wrapped_title:
        draw.text((x, y), line, fill=TITLE_COLOR, font=title_font)
        y += draw.textbbox((0, 0), line or " ", font=title_font)[3] + 10
    y += 2

    if subtitle:
        for line in wrapped_subtitle:
            draw.text((x, y), line, fill=MUTED_COLOR, font=subtitle_font)
            y += draw.textbbox((0, 0), line or " ", font=subtitle_font)[3] + 8
        y += 10

    draw.line((x, y, width - outer - inner, y), fill=BORDER, width=2)
    y += 24

    for line in wrapped_body:
        draw.text((x, y), line, fill=TEXT_COLOR, font=text_font)
        y += draw.textbbox((0, 0), line or " ", font=text_font)[3] + line_spacing

    if footer:
        y += 10
        draw.line((x, y, width - outer - inner, y), fill=BORDER, width=2)
        y += 18
        for line in wrapped_footer:
            draw.text((x, y), line, fill=MUTED_COLOR, font=footer_font)
            y += draw.textbbox((0, 0), line or " ", font=footer_font)[3] + 8

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG")
    return str(out)
