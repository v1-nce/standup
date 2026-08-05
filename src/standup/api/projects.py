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


async def _turn(client: ModelClient, project_id: str, log: ChatLog) -> None:
    log.append("assistant", await agent.converse(client, get_store(), project_id, log.read()))


@router.post("/{project_id}/chat", status_code=202)
async def send_message(project_id: str, body: ChatSend) -> jobs.Job:
    log = _chat(project_id)
    client = routes.get_client()
    log.append("user", body.content)
    return jobs.start(project_id, "thinking", _turn(client, project_id, log))
