from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class ResourceKind(str, Enum):
    FOLDER = "folder"
    FILE = "file"


class Resource(BaseModel):
    id: str
    kind: ResourceKind
    name: str
    location: str
    added_at: datetime


class Project(BaseModel):
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
    """A `command` entry is what a round actually did - the same outcome line `results` carries
    within a turn, persisted so the next turn has it too. Never written by a client; `ChatSend`
    covers what a person may put in the log."""

    role: Literal["user", "assistant", "command"]
    content: str
    at: datetime


class ProjectPaths(BaseModel):
    root: Path
    index: Path
    chat: Path
    deck: Path
    context: Path
