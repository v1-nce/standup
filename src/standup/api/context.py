"""What a project may draw on. Attaching indexes it, so the next question is answered at once."""

import asyncio
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, UploadFile

from standup.api import jobs, projects
from standup.core import index, pipeline
from standup.core.models import ContextAdd, Resource
from standup.errors import StandupError

router = APIRouter(prefix="/projects/{project_id}/context", tags=["context"])

_TURNS: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _index(project_id: str, resources: list[Resource]) -> None:
    """Only what was just attached. Merging happens per chat turn and is never stored."""
    home = projects.get_store().paths(project_id).index
    async with _TURNS[project_id]:
        for resource in resources:
            await asyncio.to_thread(index.ensure, Path(resource.location), home / resource.id)


@router.get("")
def list_context(project_id: str) -> list[Resource]:
    return projects.get_store().get(project_id).resources


@router.post("", status_code=202)
async def add_paths(project_id: str, body: ContextAdd) -> jobs.Job:
    """Folders and files by path, all of them or none — a refusal partway through would leave
    some attached and an error that says nothing about which."""
    store = projects.get_store()
    attached: list[Resource] = []
    try:
        for location in body.locations:
            attached.append(await asyncio.to_thread(store.attach_path, project_id, location))
    except StandupError:
        for undo in attached:
            await asyncio.to_thread(store.detach, project_id, undo.id)
        raise

    return jobs.start("indexing", _index(project_id, attached))


@router.post("/files", status_code=202)
async def add_files(project_id: str, files: list[UploadFile]) -> jobs.Job:
    """Kept before the job starts, so the list shows them while the indexing runs."""
    store = projects.get_store()
    attached = [
        await asyncio.to_thread(
            store.attach_file, project_id, upload.filename or "document", await upload.read()
        )
        for upload in files
    ]
    return jobs.start("indexing", _index(project_id, attached))


@router.delete("/{resource_id}", status_code=204)
async def remove_context(project_id: str, resource_id: str) -> None:
    """The resource, its copy, its index, and the deck it produced. Removed means removed."""
    store = projects.get_store()
    await asyncio.to_thread(store.detach, project_id, resource_id)
    await asyncio.to_thread(pipeline.forget, store, project_id, resource_id)
