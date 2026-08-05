from pydantic import BaseModel

from standup.core.models.artifacts import Selection, Slide


class Health(BaseModel):
    status: str


class ModelStatus(BaseModel):
    provider: str | None
    model: str
    configured: bool
    via_gateway: bool


class ModelCheck(BaseModel):
    ok: bool
    reply: str


class Deck(BaseModel):
    """A project's one deck: what it will say, and the slides once they are written."""

    selection: Selection
    slides: list[Slide] | None = None


class SelectionEdit(BaseModel):
    """The ids to keep, in the order they should appear. Anything absent is cut."""

    keep: list[str]
