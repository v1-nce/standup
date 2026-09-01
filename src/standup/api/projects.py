import asyncio
from functools import lru_cache

from fastapi import APIRouter

from standup.api import jobs, routes
from standup.config import settings
from standup.core import agent, pipeline
from standup.core.llm import ModelClient
from standup.core.models import (
    ChatMessage,
    ChatSend,
    Project,
    ProjectCreate,
    ProjectRename,
)
from standup.core.projects import ChatLog, ProjectStore

router = APIRouter(prefix="/projects", tags=["projects"])


@lru_cache(maxsize=1)
def get_store() -> ProjectStore:
    return ProjectStore(settings.projects_dir)


def _chat(project_id: str) -> ChatLog:
    store = get_store()
    store.get(project_id)
    return ChatLog(store.paths(project_id).chat)


@router.get("")
def list_projects() -> list[Project]:
    return get_store().list()


@router.post("", status_code=201)
def create_project(body: ProjectCreate) -> Project:
    return get_store().create(body.name)


@router.get("/{project_id}")
def get_project(project_id: str) -> Project:
    return get_store().get(project_id)


@router.patch("/{project_id}")
def rename_project(project_id: str, body: ProjectRename) -> Project:
    return get_store().rename(project_id, body.name)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    if jobs.busy(project_id):
        raise jobs.already_working()
    get_store().delete(project_id)
    pipeline.evict(project_id)
    jobs.evict(project_id)


@router.get("/{project_id}/chat")
def read_chat(project_id: str) -> list[ChatMessage]:
    return _chat(project_id).read()


_FAILURE_CHARS = 200


async def _turn(client: ModelClient, project_id: str, log: ChatLog) -> None:
    """The user's message is appended by `send_message` before this task is scheduled."""
    history = await asyncio.to_thread(log.read)
    try:
        reply = await agent.converse(client, get_store(), project_id, history, log=log)
    except Exception as failure:
        # A full pydantic dump can run hundreds of lines; persisting it verbatim meant every future
        # turn re-read the same giant failure as part of its own prompt, forever. Bounded here to
        # what actually helps a person reading the transcript, not the model debugging itself.
        detail = f"{type(failure).__name__}: {failure}"[:_FAILURE_CHARS]
        await asyncio.to_thread(log.append, "assistant", f"Something went wrong: {detail}")
        raise
    await asyncio.to_thread(log.append, "assistant", reply)


@router.post("/{project_id}/chat", status_code=202)
async def send_message(project_id: str, body: ChatSend) -> jobs.Job:
    with jobs.starting(project_id, exclusive=True):
        log = await asyncio.to_thread(_chat, project_id)
        client = routes.get_client()
        log.append("user", body.content)
        return jobs.start("thinking", _turn(client, project_id, log), lock=project_id)
