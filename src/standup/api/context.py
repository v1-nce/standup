"""What a project may draw on. Attaching indexes it, so the next question is answered at once."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, UploadFile

from standup.api import jobs, projects
from standup.core import index, pipeline
from standup.core.models import ContextAdd, Resource
from standup.core.projects import ProjectStore
from standup.errors import Busy, StandupError

router = APIRouter(prefix="/projects/{project_id}/context", tags=["context"])


async def _index(project_id: str, resources: list[Resource]) -> None:
    """Only what was just attached. Merging happens per chat turn and is never stored."""
    home = projects.get_store().paths(project_id).index
    async with jobs.indexing_lock(project_id):
        for resource in resources:
            await asyncio.to_thread(index.ensure, Path(resource.location), home / resource.id)


async def _detach_all(store: ProjectStore, project_id: str, attached: list[Resource]) -> None:
    """The failure path both attach routes share: whatever was kept this call, kept for nothing."""
    await asyncio.gather(*(asyncio.to_thread(store.detach, project_id, r.id) for r in attached))


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
        await _detach_all(store, project_id, attached)
        raise

    return jobs.start("indexing", _index(project_id, attached))


@router.post("/files", status_code=202)
async def add_files(project_id: str, files: list[UploadFile]) -> jobs.Job:
    """Kept before the job starts, so the list shows them while the indexing runs — all of them or
    none, the same invariant `add_paths` holds."""
    store = projects.get_store()
    attached: list[Resource] = []
    try:
        for upload in files:
            attached.append(
                await asyncio.to_thread(
                    store.attach_file, project_id, upload.filename or "document", await upload.read()
                )
            )
    except StandupError:
        await _detach_all(store, project_id, attached)
        raise

    return jobs.start("indexing", _index(project_id, attached))


@router.delete("/{resource_id}", status_code=204)
async def remove_context(project_id: str, resource_id: str) -> None:
    """The resource, its copy, its index, and the deck it produced. Removed means removed."""
    if jobs.busy(project_id):
        raise Busy(f"{project_id} is already working")
    store = projects.get_store()
    await asyncio.to_thread(store.detach, project_id, resource_id)
    await asyncio.to_thread(pipeline.forget, store, project_id, resource_id)
