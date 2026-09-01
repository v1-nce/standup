"""Render semantic slide layouts on a custom PowerPoint canvas.

The agent chooses meaning-level topology and art direction; deterministic code owns geometry,
typography, contrast, image fitting, and editability. No stock content placeholder dictates the
shape of every slide.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from standup.core.models import DeckDesign, Slide, SlidePlan, VisualElement
from standup.errors import InvalidInput

SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)
BLANK_LAYOUT = 6


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    text: str
    muted: str
    accent: str
    on_accent: str


PALETTES = {
    "technical": Palette("F5F7FB", "FFFFFF", "10233F", "607089", "2878FF", "FFFFFF"),
    "light": Palette("FCFCFA", "F1F4F0", "17211B", "5D6A62", "16856B", "FFFFFF"),
    "dark": Palette("0B1020", "171E32", "F5F7FF", "A8B1C7", "7C9CFF", "08101F"),
    "editorial": Palette("F4EFE7", "FFFDF8", "241C18", "74665D", "B54432", "FFFFFF"),
    "bold": Palette("F5F238", "FFFFFF", "111111", "555555", "FF4057", "FFFFFF"),
}


def _rgb(value: str) -> RGBColor:
    clean = value.removeprefix("#")
    return RGBColor.from_string(clean.upper())


def _palette(design: DeckDesign) -> Palette:
    base = PALETTES[design.theme]
    return Palette(
        base.background,
        base.surface,
        base.text,
        base.muted,
        design.accent.removeprefix("#") if design.accent else base.accent,
        base.on_accent,
    )


def _background(slide, color: str) -> None:
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(color)


def _rect(slide, x: float, y: float, width: float, height: float, color: str, radius=False):
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    shape.line.fill.background()
    return shape


def _text(
    slide,
    value: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    font: str,
    size: float,
    color: str,
    bold: bool = False,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = anchor
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.text = value
    if paragraph.runs:
        run = paragraph.runs[0]
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = _rgb(color)
    return shape


def _bullets(
    slide,
    values: list[str],
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    design: DeckDesign,
    palette: Palette,
    color: str | None = None,
    size: float = 20,
) -> None:
    if not values:
        return
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    for index, value in enumerate(values):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = f"•  {value}"
        paragraph.space_after = Pt(14)
        if paragraph.runs:
            run = paragraph.runs[0]
            run.font.name = design.body_font
            run.font.size = Pt(size)
            run.font.color.rgb = _rgb(color or palette.text)


def _label(slide, value: str, x: float, y: float, design: DeckDesign, palette: Palette) -> None:
    _text(
        slide,
        value.upper(),
        x,
        y,
        3.5,
        0.35,
        font=design.body_font,
        size=10,
        color=palette.accent,
        bold=True,
    )


def _footer(slide, position: int, design: DeckDesign, palette: Palette) -> None:
    _rect(slide, 0.7, 7.12, 0.32, 0.04, palette.accent)
    _text(
        slide,
        f"{position:02d}",
        11.95,
        6.95,
        0.65,
        0.25,
        font=design.body_font,
        size=9,
        color=palette.muted,
        align=PP_ALIGN.RIGHT,
    )


def _picture(slide, path: Path, x: float, y: float, width: float, height: float):
    try:
        with Image.open(path) as image:
            image_width, image_height = image.size
    except (OSError, ValueError) as failure:
        raise InvalidInput(f"Image {path.name!r} could not be rendered: {failure}") from failure
    image_ratio = image_width / image_height
    box_ratio = width / height
    if image_ratio >= box_ratio:
        fitted_width = width
        fitted_height = width / image_ratio
    else:
        fitted_height = height
        fitted_width = height * image_ratio
    return slide.shapes.add_picture(
        str(path),
        Inches(x + (width - fitted_width) / 2),
        Inches(y + (height - fitted_height) / 2),
        width=Inches(fitted_width),
        height=Inches(fitted_height),
    )


def _color(value: str, palette: Palette) -> str | None:
    if value == "transparent":
        return None
    if value.startswith("#"):
        return value.removeprefix("#")
    return {
        "background": palette.background,
        "surface": palette.surface,
        "text": palette.text,
        "muted": palette.muted,
        "accent": palette.accent,
        "on_accent": palette.on_accent,
    }[value]


def _canvas_shape(added, element: VisualElement, palette: Palette) -> None:
    shapes = {
        "rectangle": MSO_SHAPE.RECTANGLE,
        "rounded": MSO_SHAPE.ROUNDED_RECTANGLE,
        "ellipse": MSO_SHAPE.OVAL,
        "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE,
        "chevron": MSO_SHAPE.CHEVRON,
    }
    shape = added.shapes.add_shape(
        shapes[element.shape],
        Inches(element.x * 13.333 / 100),
        Inches(element.y * 7.5 / 100),
        Inches(element.width * 13.333 / 100),
        Inches(element.height * 7.5 / 100),
    )
    fill = _color(element.fill, palette)
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(fill)
    else:
        shape.fill.background()
    stroke = _color(element.stroke, palette)
    if stroke and element.stroke_width:
        shape.line.color.rgb = _rgb(stroke)
        shape.line.width = Pt(element.stroke_width)
    else:
        shape.line.fill.background()
    shape.rotation = element.rotation


def _canvas_line(added, element: VisualElement, palette: Palette) -> None:
    x = element.x * 13.333 / 100
    y = element.y * 7.5 / 100
    line = added.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x),
        Inches(y),
        Inches(x + element.width * 13.333 / 100),
        Inches(y + element.height * 7.5 / 100),
    )
    stroke = _color(element.stroke, palette) or palette.text
    line.line.color.rgb = _rgb(stroke)
    line.line.width = Pt(element.stroke_width or 1)
    line.rotation = element.rotation


def _canvas_text(added, element: VisualElement, design: DeckDesign, palette: Palette) -> None:
    align = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
    anchor = {
        "top": MSO_ANCHOR.TOP,
        "middle": MSO_ANCHOR.MIDDLE,
        "bottom": MSO_ANCHOR.BOTTOM,
    }
    shape = _text(
        added,
        element.text,
        element.x * 13.333 / 100,
        element.y * 7.5 / 100,
        element.width * 13.333 / 100,
        element.height * 7.5 / 100,
        font=element.font_family or design.body_font,
        size=element.font_size,
        color=_color(element.color, palette) or palette.text,
        bold=element.font_weight in {"semibold", "bold"},
        align=align[element.align],
        anchor=anchor[element.valign],
    )
    shape.rotation = element.rotation


def _canvas(
    added,
    slide: Slide,
    design: DeckDesign,
    palette: Palette,
    images: dict[str, Path],
) -> None:
    for element in slide.elements:
        if element.kind == "shape":
            _canvas_shape(added, element, palette)
        elif element.kind == "line":
            _canvas_line(added, element, palette)
        elif element.kind == "text":
            _canvas_text(added, element, design, palette)
        elif element.kind == "image":
            path = images.get(element.image or "")
            if path is None or not path.is_file():
                raise InvalidInput(
                    f"{slide.candidate_id}: image {element.image!r} not found on disk"
                )
            _picture(
                added,
                path,
                element.x * 13.333 / 100,
                element.y * 7.5 / 100,
                element.width * 13.333 / 100,
                element.height * 7.5 / 100,
            ).rotation = element.rotation


def _layout(slide: Slide) -> str:
    if slide.layout != "auto":
        return slide.layout
    if slide.image:
        return "image"
    if slide.secondary_bullets:
        return "two_column"
    if slide.free and not slide.bullets:
        return "cover"
    if len(slide.bullets) <= 1:
        return "statement"
    return "content"


def _cover(added, slide: Slide, design: DeckDesign, palette: Palette) -> None:
    _rect(added, 0, 0, 0.28, 7.5, palette.accent)
    _rect(added, 10.9, 0.72, 1.75, 1.75, palette.surface, radius=True)
    _rect(added, 11.35, 1.17, 0.85, 0.85, palette.accent, radius=True)
    _label(added, slide.subtitle or "Standup", 0.95, 1.1, design, palette)
    _text(
        added,
        slide.title,
        0.95,
        1.65,
        9.8,
        2.5,
        font=design.heading_font,
        size=42,
        color=palette.text,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    _bullets(added, slide.bullets, 0.98, 4.65, 8.7, 1.4, design=design, palette=palette, size=17)


def _section(added, slide: Slide, design: DeckDesign, palette: Palette, position: int) -> None:
    _background(added, palette.accent)
    _text(
        added,
        f"{position:02d}",
        0.85,
        0.55,
        2.2,
        1.3,
        font=design.heading_font,
        size=58,
        color=palette.on_accent,
        bold=True,
    )
    _text(
        added,
        slide.title,
        3.0,
        1.65,
        8.9,
        2.2,
        font=design.heading_font,
        size=38,
        color=palette.on_accent,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    _text(
        added,
        slide.subtitle,
        3.05,
        4.15,
        7.6,
        0.9,
        font=design.body_font,
        size=19,
        color=palette.on_accent,
    )


def _content(added, slide: Slide, design: DeckDesign, palette: Palette) -> None:
    _label(added, slide.subtitle or "Key update", 0.75, 0.55, design, palette)
    _text(
        added,
        slide.title,
        0.75,
        1.0,
        8.0,
        1.2,
        font=design.heading_font,
        size=30,
        color=palette.text,
        bold=True,
    )
    _bullets(added, slide.bullets, 0.82, 2.45, 7.7, 3.8, design=design, palette=palette, size=20)
    _rect(added, 9.15, 0.7, 3.45, 5.95, palette.surface, radius=True)
    _rect(added, 9.48, 1.02, 0.5, 0.12, palette.accent, radius=True)
    takeaway = slide.subtitle or (slide.bullets[0] if slide.bullets else slide.title)
    _text(
        added,
        takeaway,
        9.48,
        1.55,
        2.7,
        3.9,
        font=design.heading_font,
        size=23,
        color=palette.text,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def _two_column(added, slide: Slide, design: DeckDesign, palette: Palette) -> None:
    _label(added, slide.subtitle or "Two perspectives", 0.75, 0.5, design, palette)
    _text(
        added,
        slide.title,
        0.75,
        0.9,
        11.7,
        1.0,
        font=design.heading_font,
        size=29,
        color=palette.text,
        bold=True,
    )
    left = slide.bullets
    right = slide.secondary_bullets
    if not right and len(left) > 1:
        midpoint = (len(left) + 1) // 2
        left, right = left[:midpoint], left[midpoint:]
    for x in (0.72, 6.75):
        _rect(added, x, 2.15, 5.82, 4.45, palette.surface, radius=True)
    _text(
        added,
        "What changed",
        1.08,
        2.52,
        4.95,
        0.55,
        font=design.heading_font,
        size=17,
        color=palette.accent,
        bold=True,
    )
    _text(
        added,
        slide.secondary_title or "Why it matters",
        7.1,
        2.52,
        4.95,
        0.55,
        font=design.heading_font,
        size=17,
        color=palette.accent,
        bold=True,
    )
    _bullets(added, left, 1.08, 3.3, 4.85, 2.75, design=design, palette=palette, size=17)
    _bullets(added, right, 7.1, 3.3, 4.85, 2.75, design=design, palette=palette, size=17)


def _statement(added, slide: Slide, design: DeckDesign, palette: Palette) -> None:
    _rect(added, 0.78, 0.75, 0.18, 5.85, palette.accent)
    _label(added, slide.subtitle or "Takeaway", 1.35, 1.0, design, palette)
    _text(
        added,
        slide.title,
        1.35,
        1.55,
        10.5,
        3.15,
        font=design.heading_font,
        size=38,
        color=palette.text,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    _bullets(added, slide.bullets, 1.4, 5.1, 9.8, 1.1, design=design, palette=palette, size=17)


def _image_layout(
    added,
    slide: Slide,
    design: DeckDesign,
    palette: Palette,
    images: dict[str, Path],
) -> None:
    if not slide.image:
        raise InvalidInput(f"{slide.candidate_id}: image layout needs an image")
    path = images.get(slide.image)
    if path is None or not path.is_file():
        raise InvalidInput(f"{slide.candidate_id}: image {slide.image!r} not found on disk")
    _rect(added, 6.55, 0, 6.78, 7.5, palette.surface)
    _picture(added, path, 6.8, 0.45, 6.15, 6.6)
    _label(added, slide.subtitle or "Visual", 0.72, 0.65, design, palette)
    _text(
        added,
        slide.title,
        0.72,
        1.2,
        5.3,
        1.7,
        font=design.heading_font,
        size=29,
        color=palette.text,
        bold=True,
    )
    _bullets(added, slide.bullets, 0.78, 3.3, 5.1, 2.8, design=design, palette=palette, size=17)


def build(plan: SlidePlan, destination: Path, images: dict[str, Path] | None = None) -> Path:
    images = images or {}
    deck = Presentation()
    deck.slide_width = SLIDE_WIDTH
    deck.slide_height = SLIDE_HEIGHT
    design = plan.design
    palette = _palette(design)

    for position, slide in enumerate(plan.slides, start=1):
        added = deck.slides.add_slide(deck.slide_layouts[BLANK_LAYOUT])
        _background(added, palette.background)
        layout = _layout(slide)
        if slide.elements:
            _canvas(added, slide, design, palette, images)
        elif layout == "cover":
            _cover(added, slide, design, palette)
        elif layout == "section":
            _section(added, slide, design, palette, position)
        elif layout == "two_column":
            _two_column(added, slide, design, palette)
        elif layout == "statement":
            _statement(added, slide, design, palette)
        elif layout == "image":
            _image_layout(added, slide, design, palette, images)
        else:
            _content(added, slide, design, palette)
        if not slide.elements and layout not in {"cover", "section"}:
            _footer(added, position, design, palette)
        if slide.speaker_notes:
            added.notes_slide.notes_text_frame.text = slide.speaker_notes

    destination.parent.mkdir(parents=True, exist_ok=True)
    deck.save(str(destination))
    return destination
