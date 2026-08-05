"""A project's one deck. Reading and editing it never calls the model — only the chat does."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from standup.api import projects
from standup.core import pipeline
from standup.core.models import Deck, SelectionEdit

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@router.get("")
def read_deck(project_id: str) -> Deck:
    return pipeline.read(projects.get_store(), project_id)


@router.put("/selection")
def edit_selection(project_id: str, body: SelectionEdit) -> Deck:
    return pipeline.edit(projects.get_store(), project_id, body.keep)


@router.get("/file")
def download_deck(project_id: str) -> FileResponse:
    written = pipeline.render(projects.get_store(), project_id)
    return FileResponse(written, media_type=PPTX, filename=written.name)
