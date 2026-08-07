from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class ResourceKind(str, Enum):
    FOLDER = "folder"
    FILE = "file"


class Resource(BaseModel):
    """One thing a project may draw on. `id` prefixes every path derived from it."""

    id: str
    kind: ResourceKind
    name: str
    location: str
    added_at: datetime


class Project(BaseModel):
    """`resources` is what the project may talk about. Empty until something is attached."""

    id: str
    name: str
    created_at: datetime
    resources: list[Resource] = []


class ProjectCreate(BaseModel):
    name: str


class ProjectRename(BaseModel):
    name: str


class ContextAdd(BaseModel):
    """Paths on this machine — folders, files, or a mix of both."""

    locations: list[str]


class ChatSend(BaseModel):
    """What a client may put in the log. Only the person's own words — never a reply."""

    content: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    at: datetime


class ProjectPaths(BaseModel):
    root: Path
    index: Path
    chat: Path
    deck: Path
    context: Path
