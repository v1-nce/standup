from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class SourceKind(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


class Source(BaseModel):
    kind: SourceKind
    location: str
    has_git: bool


class Project(BaseModel):
    """`source` is what the project was given to talk about. None until something is attached."""

    id: str
    name: str
    created_at: datetime
    source: Source | None = None


class ProjectCreate(BaseModel):
    name: str


class ProjectRename(BaseModel):
    name: str


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
    clone: Path
