from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class SourceKind(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


class Source(BaseModel):
    kind: SourceKind
    location: str
    has_git: bool


class Project(BaseModel):
    id: str
    name: str
    created_at: datetime
    source: Source


class ProjectCreate(BaseModel):
    name: str
    location: str


class ChatAppend(BaseModel):
    role: str
    content: str


class ChatMessage(ChatAppend):
    at: datetime


class ProjectPaths(BaseModel):
    root: Path
    index: Path
    chat: Path
    decks: Path
    clone: Path
