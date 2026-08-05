"""What the agent may do to a deck. Choosing is the model's; doing is deterministic."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from standup.core import pipeline
from standup.core.models import Deck, Index, Scope, Slide
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
    """Slide text. Only the slides named here change; the rest are left byte for byte."""

    action: Literal["write"]
    slides: list[Slide]


Command = Annotated[Select | Keep | Write, Field(discriminator="action")]


def _standing(deck: Deck) -> str:
    wanted = [entry.candidate.id for entry in deck.selection.chosen]
    written = {slide.candidate_id for slide in deck.slides or []}
    missing = [item for item in wanted if item not in written]
    if missing:
        return f"{len(wanted)} chosen; still to write: {missing}"
    return f"{len(wanted)} chosen, all written"


def apply(store: ProjectStore, project_id: str, index: Index | None, command: Command) -> str:
    """One command, and the line the model reads next. Its own mistakes come back as text."""
    if index is None:
        return f"{command.action} rejected: this project has nothing attached to build a deck from"
    try:
        match command:
            case Select():
                deck = pipeline.select(store, project_id, index, command.request, command.scope)
                return f"select: {_standing(deck)}; {len(deck.selection.cut)} cut"
            case Keep():
                return f"keep: {_standing(pipeline.edit(store, project_id, command.ids))}"
            case Write():
                deck = pipeline.write(store, project_id, index, command.slides)
                return f"write: {_standing(deck)}"
    except (InvalidInput, NotFound) as mistake:
        return f"{command.action} rejected: {mistake}"
