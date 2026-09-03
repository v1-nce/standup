"""The pipeline's spine: index → scope → candidates → selection → slide plan."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Symbol(BaseModel):
    name: str
    kind: str
    line: int


class FileFacts(BaseModel):
    path: str
    content_hash: str
    symbols: list[Symbol] = []
    imports: list[str] = []
    excerpt: str = ""


class Commit(BaseModel):
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
    paths: list[str] = []
    commits: list[str] = []


class Scored(BaseModel):
    candidate: Candidate
    signals: dict[str, float] = {}
    score: float
    # Set only on a cut item - narrates its dominant signal and gap to the cutoff, for a human
    # reading the selection panel. Never set on a chosen item; never shown to the model.
    reason: str | None = None


class Selection(BaseModel):
    """What the deck will say and why — visible and editable before anything renders."""

    request: str
    scope: Scope
    chosen: list[Scored] = []
    cut: list[Scored] = []


SlideLayout = Literal[
    "auto", "cover", "section", "content", "two_column", "statement", "image"
]
DeckTheme = Literal["technical", "light", "dark", "editorial", "bold"]
ElementKind = Literal["text", "shape", "line", "image"]
ShapeKind = Literal["rectangle", "rounded", "ellipse", "triangle", "chevron"]
TextAlign = Literal["left", "center", "right"]
VerticalAlign = Literal["top", "middle", "bottom"]
FontWeight = Literal["regular", "semibold", "bold"]
_COLOR = r"^(?:#[0-9A-Fa-f]{6}|background|surface|text|muted|accent|on_accent|transparent)$"


class DeckDesign(BaseModel):
    """Deck-level art direction. Layout remains semantic; code owns the pixel geometry."""

    theme: DeckTheme = "technical"
    accent: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    heading_font: str = Field(default="Aptos Display", min_length=1, max_length=80)
    body_font: str = Field(default="Aptos", min_length=1, max_length=80)


class VisualElement(BaseModel):
    """One editable layer on a normalized 100×100 slide canvas."""

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    kind: ElementKind
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(ge=0, le=100)
    height: float = Field(ge=0, le=100)
    text: str = ""
    image: str | None = None
    shape: ShapeKind = "rectangle"
    fill: str = Field(default="transparent", pattern=_COLOR)
    stroke: str = Field(default="transparent", pattern=_COLOR)
    stroke_width: float = Field(default=0, ge=0, le=8)
    color: str = Field(default="text", pattern=_COLOR)
    font_size: float = Field(default=20, ge=6, le=96)
    font_weight: FontWeight = "regular"
    font_family: str | None = Field(default=None, min_length=1, max_length=80)
    align: TextAlign = "left"
    valign: VerticalAlign = "top"
    rotation: float = Field(default=0, ge=-180, le=180)

    @model_validator(mode="after")
    def valid_geometry_and_content(self):
        if self.x + self.width > 100 or self.y + self.height > 100:
            raise ValueError("element must remain inside the 100×100 canvas")
        if self.kind == "line":
            if self.width == 0 and self.height == 0:
                raise ValueError("a line needs a non-zero width or height")
        elif self.width == 0 or self.height == 0:
            raise ValueError(f"a {self.kind} element needs non-zero width and height")
        if self.kind == "text" and not self.text.strip():
            raise ValueError("a text element needs text")
        if self.kind == "image" and not self.image:
            raise ValueError("an image element needs an attached image id")
        return self


class Slide(BaseModel):
    candidate_id: str
    free: bool = False
    title: str
    subtitle: str = ""
    bullets: list[str] = []
    secondary_title: str = ""
    secondary_bullets: list[str] = []
    image: str | None = None
    layout: SlideLayout = "auto"
    speaker_notes: str = ""
    elements: list[VisualElement] = []

    @model_validator(mode="after")
    def unique_element_ids(self):
        ids = [element.id for element in self.elements]
        if len(ids) != len(set(ids)):
            raise ValueError("visual element ids must be unique within a slide")
        return self


class SlidePlan(BaseModel):
    design: DeckDesign = DeckDesign()
    slides: list[Slide] = []


class MemoryEntry(BaseModel):
    """One editorial decision — what a `keep` held and what it dropped — recorded so the next
    deck can reuse the project's own history. Kept and cut hold candidate ids only, never free-slide
    ids, which are presentation order rather than evidence preference."""

    at: datetime
    request: str
    kept: list[str] = []
    cut: list[str] = []


class Memory(BaseModel):
    """A project's preference trace, stored as an inspectable, editable artifact. Evolution here is
    a visible record, not a hidden model change: delete or edit `entries` to revert it."""

    entries: list[MemoryEntry] = []
