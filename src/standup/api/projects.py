import asyncio
from functools import lru_cache

from fastapi import APIRouter

from standup.api import jobs, routes
from standup.config import settings
from standup.core import agent
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
    get_store().delete(project_id)


@router.get("/{project_id}/chat")
def read_chat(project_id: str) -> list[ChatMessage]:
    return _chat(project_id).read()


async def _turn(client: ModelClient, project_id: str, log: ChatLog, content: str) -> None:
    """Appends the user's message itself, so a turn `jobs.start` refuses never touches the log.
    A failure past that point still closes the turn, so the log never ends on a question nobody
    answered."""
    history = await asyncio.to_thread(log.append_and_read, "user", content)
    try:
        reply = await agent.converse(client, get_store(), project_id, history)
    except Exception as failure:
        await asyncio.to_thread(log.append, "assistant", f"Something went wrong: {failure}")
        raise
    await asyncio.to_thread(log.append, "assistant", reply)


@router.post("/{project_id}/chat", status_code=202)
async def send_message(project_id: str, body: ChatSend) -> jobs.Job:
    log = await asyncio.to_thread(_chat, project_id)
    client = routes.get_client()
    return jobs.start("thinking", _turn(client, project_id, log, body.content), lock=project_id)
