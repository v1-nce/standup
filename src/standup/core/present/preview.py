"""Render the deck to a single PNG contact sheet so the model can see its own work.

Pillow-only and deliberately simple: the point is visual feedback — hierarchy, density, colour,
what is empty — not a pixel-perfect copy of the `.pptx` renderer.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from standup.core.models import SlidePlan
from standup.core.present.deck import PALETTES

WIDTH, HEIGHT = 640, 360


def _font(size: int, bold: bool = False):
    names = (
        ("DejaVuSans-Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "arial.ttf")
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex(token: str) -> str:
    return token if token.startswith("#") else "#" + token


def _tone(token: str, palette, fallback: str) -> str | None:
    if token == "transparent":
        return None
    if token.startswith("#"):
        return _hex(token)
    return _hex(
        {
            "background": palette.background,
            "surface": palette.surface,
            "text": palette.text,
            "muted": palette.muted,
            "accent": palette.accent,
            "on_accent": palette.on_accent,
        }.get(token, fallback)
    )


def _slide(plan: SlidePlan, index: int) -> Image.Image:
    slide = plan.slides[index]
    palette = PALETTES[plan.design.theme]
    image = Image.new("RGB", (WIDTH, HEIGHT), _hex(palette.background))
    draw = ImageDraw.Draw(image)

    draw.rectangle([0, 0, 12, HEIGHT], fill=_hex(palette.accent))
    draw.text((44, 34), slide.title, fill=_hex(palette.text), font=_font(32, bold=True))
    if slide.subtitle:
        draw.text((44, 86), slide.subtitle.upper(), fill=_hex(palette.accent), font=_font(13, bold=True))

    y = 130
    for bullet in slide.bullets[:6]:
        draw.text((52, y), "• " + bullet, fill=_hex(palette.muted), font=_font(19))
        y += 32

    for element in slide.elements:
        if element.kind != "text":
            continue
        draw.text(
            (element.x * WIDTH // 100, element.y * HEIGHT // 100),
            element.text[:60],
            fill=_tone(element.color or "text", palette, palette.text) or _hex(palette.text),
            font=_font(15),
        )
    return image


def contact_sheet(plan: SlidePlan) -> bytes:
    """One stacked PNG of every slide, so a single vision call can review the whole deck."""
    slides = plan.slides or []
    height = HEIGHT * max(1, len(slides))
    sheet = Image.new("RGB", (WIDTH, height), "#FFFFFF")
    for index in range(len(slides)):
        sheet.paste(_slide(plan, index), (0, index * HEIGHT))
    buffer = BytesIO()
    sheet.save(buffer, format="PNG")
    return buffer.getvalue()
