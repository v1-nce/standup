import asyncio
from functools import lru_cache

from fastapi import APIRouter

from config import settings
from models import ChatAppend, ChatMessage, Project, ProjectCreate
from projects import ChatLog, ProjectStore

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
async def create_project(body: ProjectCreate) -> Project:
    return await asyncio.to_thread(get_store().create, body.name, body.location)


@router.get("/{project_id}")
def get_project(project_id: str) -> Project:
    return get_store().get(project_id)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    get_store().delete(project_id)


@router.get("/{project_id}/chat")
def read_chat(project_id: str) -> list[ChatMessage]:
    return _chat(project_id).read()


@router.post("/{project_id}/chat", status_code=201)
def append_chat(project_id: str, message: ChatAppend) -> ChatMessage:
    return _chat(project_id).append(message.role, message.content)
