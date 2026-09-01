from pydantic import BaseModel

from standup.core.models.artifacts import DeckDesign, Selection, Slide


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
    selection: Selection
    design: DeckDesign = DeckDesign()
    slides: list[Slide] | None = None


class SelectionEdit(BaseModel):
    keep: list[str]
