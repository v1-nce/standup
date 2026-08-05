"""The pipeline's spine: index → scope → candidates → briefs → selection → slide plan."""

from datetime import datetime

from pydantic import BaseModel, Field


class Symbol(BaseModel):
    name: str
    kind: str
    line: int


class FileFacts(BaseModel):
    path: str
    content_hash: str
    symbols: list[Symbol] = []
    imports: list[str] = []


class Commit(BaseModel):
    """`changes` maps each path to the lines it gained or lost, never the commit's total."""

    sha: str
    authored_at: datetime
    author: str
    message: str
    changes: dict[str, int] = {}


class Index(BaseModel):
    """Every derived fact about a project. Built on registration and on change, never per deck."""

    fingerprint: str
    built_at: datetime
    files: list[FileFacts] = []
    commits: list[Commit] = []
    history_complete: bool = True
    rank: dict[str, float] = {}
    emphasis: dict[str, float] = {}


class Scope(BaseModel):
    """What the request puts in play — the one model output that precedes any derived work."""

    since: datetime | None = None
    until: datetime | None = None
    paths: list[str] = []
    keywords: list[str] = []
    audience: str | None = None
    slide_budget: int = Field(ge=1)


class Candidate(BaseModel):
    id: str
    title: str
    paths: list[str] = []
    commits: list[str] = []


class Brief(BaseModel):
    """One candidate examined blind to the others. `evidence` is what validation checks."""

    candidate_id: str
    what_changed: str
    why_it_matters: str
    evidence: list[str] = []


class Scored(BaseModel):
    candidate: Candidate
    brief: Brief | None = None
    signals: dict[str, float] = {}
    score: float


class Selection(BaseModel):
    """What the deck will say and why — visible and editable before anything renders."""

    request: str
    scope: Scope
    chosen: list[Scored] = []
    cut: list[Scored] = []


class Slide(BaseModel):
    candidate_id: str
    title: str
    bullets: list[str] = []


class SlidePlan(BaseModel):
    slides: list[Slide] = []
