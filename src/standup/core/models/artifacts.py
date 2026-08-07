"""The pipeline's spine: index → scope → candidates → selection → slide plan."""

from datetime import datetime

from pydantic import BaseModel, Field


class Symbol(BaseModel):
    name: str
    kind: str
    line: int


class FileFacts(BaseModel):
    """`excerpt` is filled only for a file attached on its own, whose text is its whole evidence."""

    path: str
    content_hash: str
    symbols: list[Symbol] = []
    imports: list[str] = []
    excerpt: str = ""


class Commit(BaseModel):
    """`changes` maps each path to the lines it gained or lost, never the commit's total."""

    sha: str
    authored_at: datetime
    author: str
    message: str
    changes: dict[str, int] = {}


class Facts(BaseModel):
    """One resource's derived facts, cached beside it. Ranking waits for the merge — it is
    relative, and a three-file folder must not outrank a three-thousand-file repository."""

    fingerprint: str
    built_at: datetime
    files: list[FileFacts] = []
    commits: list[Commit] = []
    history_complete: bool = True
    aliases: dict[str, str] = {}
    text: str = ""


class Index(BaseModel):
    """Every derived fact about a project: its resources merged, then ranked as one."""

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


class Scored(BaseModel):
    candidate: Candidate
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
