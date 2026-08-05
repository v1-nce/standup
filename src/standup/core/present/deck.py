"""A SlidePlan becomes a .pptx. Layouts come from the template; python-pptx cannot create them."""

from pathlib import Path

from pptx import Presentation

from standup.core.models import SlidePlan
from standup.errors import InvalidInput

TITLE_AND_CONTENT = 1
BODY_PLACEHOLDER = 1


def build(plan: SlidePlan, destination: Path) -> Path:
    deck = Presentation()
    layout = deck.slide_layouts[TITLE_AND_CONTENT]

    for slide in plan.slides:
        added = deck.slides.add_slide(layout)
        added.shapes.title.text = slide.title

        body = next(
            (
                shape
                for shape in added.placeholders
                if shape.placeholder_format.idx == BODY_PLACEHOLDER
            ),
            None,
        )
        if body is None:
            raise InvalidInput(f"Layout {TITLE_AND_CONTENT} has no body to put bullets in")

        frame = body.text_frame
        frame.text = slide.bullets[0] if slide.bullets else ""
        for bullet in slide.bullets[1:]:
            frame.add_paragraph().text = bullet

    destination.parent.mkdir(parents=True, exist_ok=True)
    deck.save(str(destination))
    return destination
