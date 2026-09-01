"""What the agent may do to a deck. Choosing is the model's; doing is deterministic."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from standup.core import pipeline
from standup.core.models import (
    Deck,
    DeckDesign,
    Index,
    Scope,
    Slide,
    SlideLayout,
    VisualElement,
)
from standup.core.projects import ProjectStore
from standup.errors import InvalidInput, NotFound


class Select(BaseModel):
    """Re-derive what the deck is about. Slides written against the old scope are discarded."""

    action: Literal["select"]
    request: str
    scope: Scope


class Keep(BaseModel):
    """The exact ids the deck should hold, in slide order. Anything absent is cut."""

    action: Literal["keep"]
    ids: list[str]


class Write(BaseModel):
    """Create or replace named slides; every unnamed slide remains byte-for-byte unchanged."""

    action: Literal["write"]
    slides: list[Slide]
    design: DeckDesign | None = None


class Update(BaseModel):
    """Patch one slide. Omitted fields remain byte-for-byte unchanged."""

    action: Literal["update"]
    slide_id: str
    title: str | None = None
    subtitle: str | None = None
    bullets: list[str] | None = None
    secondary_title: str | None = None
    secondary_bullets: list[str] | None = None
    image: str | None = None
    clear_image: bool = False
    layout: SlideLayout | None = None
    speaker_notes: str | None = None
    upsert_elements: list[VisualElement] = []
    remove_element_ids: list[str] = []


class Style(BaseModel):
    """Change deck-level art direction without touching slide content."""

    action: Literal["style"]
    design: DeckDesign


Command = Annotated[Select | Keep | Write | Update | Style, Field(discriminator="action")]


def _standing(deck: Deck) -> str:
    wanted = [entry.candidate.id for entry in deck.selection.chosen]
    written = {slide.candidate_id for slide in deck.slides or []}
    missing = [item for item in wanted if item not in written]
    if missing:
        return f"{len(wanted)} chosen; still to write: {missing}"
    return f"{len(wanted)} chosen, all written"


def echo(command: Command) -> str:
    """What the model actually asked for.

    Each round is a fresh call carrying no assistant turn, so an outcome on its own is a verdict on
    something the model cannot remember proposing. Naming the command beside its result is what lets
    "do not repeat it" mean anything.
    """
    match command:
        case Select():
            return f"select(budget={command.scope.slide_budget}, request={command.request!r})"
        case Keep():
            return f"keep({command.ids})"
        case Write():
            return f"write({[slide.candidate_id for slide in command.slides]})"
        case Update():
            return f"update({command.slide_id!r})"
        case Style():
            return f"style({command.design.theme!r})"


def apply(store: ProjectStore, project_id: str, index: Index | None, command: Command) -> str:
    """One command, and the line the model reads next. Its own mistakes come back as text."""
    if index is None:
        return f"{echo(command)} rejected: this project has nothing attached to build a deck from"
    try:
        match command:
            case Select():
                deck = pipeline.select(store, project_id, index, command.request, command.scope)
                return f"{echo(command)} -> {_standing(deck)}; {len(deck.selection.cut)} cut"
            case Keep():
                return f"{echo(command)} -> {_standing(pipeline.edit(store, project_id, command.ids))}"
            case Write():
                uncomposed = [slide.candidate_id for slide in command.slides if not slide.elements]
                if uncomposed:
                    return (
                        f"{echo(command)} rejected: every newly written slide needs a non-empty "
                        f"canvas composition; missing elements for {uncomposed}"
                    )
                deck = pipeline.write(store, project_id, index, command.slides, command.design)
                return f"{echo(command)} -> {_standing(deck)}"
            case Update():
                fields = (
                    "title",
                    "subtitle",
                    "bullets",
                    "secondary_title",
                    "secondary_bullets",
                    "image",
                    "layout",
                    "speaker_notes",
                )
                changes = {
                    field: getattr(command, field)
                    for field in fields
                    if getattr(command, field) is not None
                }
                if command.clear_image:
                    changes["image"] = None
                if not changes and not command.upsert_elements and not command.remove_element_ids:
                    return f"{echo(command)} rejected: no slide fields were provided"
                deck = pipeline.update(
                    store,
                    project_id,
                    index,
                    command.slide_id,
                    changes,
                    command.upsert_elements,
                    command.remove_element_ids,
                )
                return f"{echo(command)} -> {_standing(deck)}"
            case Style():
                deck = pipeline.style(store, project_id, command.design)
                return f"{echo(command)} -> {_standing(deck)}"
    except (InvalidInput, NotFound) as mistake:
        return f"{echo(command)} rejected: {mistake}"
    except Exception as failure:  # noqa: BLE001
        # Anything else used to escape `converse` and discard every command that already succeeded
        # this turn. It comes back as a line instead, so the turn keeps what it earned.
        return f"{echo(command)} rejected: {type(failure).__name__}: {failure}"
