from pydantic import BaseModel, Field

from models.artifacts import Selection


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


class DeckRequest(BaseModel):
    request: str
    slide_budget: int = Field(default=5, ge=1)


class DeckProposal(BaseModel):
    deck_id: str
    selection: Selection


class SelectionEdit(BaseModel):
    """The ids to keep, in the order they should appear. Anything absent is cut."""

    keep: list[str]
