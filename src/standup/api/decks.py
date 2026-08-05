"""Propose a deck, change your mind, then build it."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from standup.api.projects import get_store
from standup.api.routes import get_client
from standup.core import pipeline
from standup.core.models import DeckProposal, DeckRequest, Selection, SelectionEdit

router = APIRouter(prefix="/projects/{project_id}/decks", tags=["decks"])

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@router.post("", status_code=201)
async def propose_deck(project_id: str, body: DeckRequest) -> DeckProposal:
    deck_id, selection = await pipeline.propose(
        get_client(), get_store(), project_id, body.request, slide_budget=body.slide_budget
    )
    return DeckProposal(deck_id=deck_id, selection=selection)


@router.get("/{deck_id}")
def read_selection(project_id: str, deck_id: str) -> Selection:
    return pipeline.load(get_store(), project_id, deck_id)


@router.put("/{deck_id}/selection")
def edit_selection(project_id: str, deck_id: str, body: SelectionEdit) -> Selection:
    return pipeline.edit(get_store(), project_id, deck_id, body.keep)


@router.post("/{deck_id}/build")
async def build_deck(project_id: str, deck_id: str) -> FileResponse:
    written = await pipeline.build(get_client(), get_store(), project_id, deck_id)
    return FileResponse(written, media_type=PPTX, filename=written.name)
