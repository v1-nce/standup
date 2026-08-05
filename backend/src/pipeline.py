"""The four stages, stitched. Proposing and building are separate so the selection can be seen."""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import index as index_module
import selection as selection_module
from errors import NotFound
from gather import candidates, scope
from llm import ModelClient
from models import Index, Selection, SlidePlan
from present import build as build_deck
from present import plan as plan_slides
from present import revise
from projects import ProjectStore

SELECTION_FILE = "selection.json"
PLAN_FILE = "plan.json"
DECK_FILE = "deck.pptx"


def _identify(request: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{request}\n{fingerprint}".encode()).hexdigest()[:8]


def _room(store: ProjectStore, project_id: str, deck_id: str) -> Path:
    return store.paths(project_id).decks / deck_id


async def _indexed(store: ProjectStore, project_id: str) -> Index:
    # Parsing a repo takes seconds; it must not sit on the event loop.
    return await asyncio.to_thread(
        index_module.ensure, store.working_tree(project_id), store.paths(project_id).index
    )


async def propose(
    client: ModelClient,
    store: ProjectStore,
    project_id: str,
    request: str,
    *,
    slide_budget: int,
    today: datetime | None = None,
) -> tuple[str, Selection]:
    """Everything up to the decision. One model call, and the result is yours to change."""
    index = await _indexed(store, project_id)
    settled = await scope(
        client,
        request,
        index=index,
        today=today or datetime.now(UTC),
        slide_budget=slide_budget,
    )
    chosen = selection_module.choose(
        index, settled, candidates(index, settled), request=request
    )

    deck_id = _identify(request, index.fingerprint)
    room = _room(store, project_id, deck_id)
    room.mkdir(parents=True, exist_ok=True)
    (room / SELECTION_FILE).write_text(chosen.model_dump_json(indent=2), encoding="utf-8")
    return deck_id, chosen


def load(store: ProjectStore, project_id: str, deck_id: str) -> Selection:
    record = _room(store, project_id, deck_id) / SELECTION_FILE
    if not record.is_file():
        raise NotFound(f"No deck {deck_id} in {project_id}")
    return Selection.model_validate_json(record.read_text(encoding="utf-8"))


def edit(store: ProjectStore, project_id: str, deck_id: str, keep: list[str]) -> Selection:
    revised = selection_module.edited(load(store, project_id, deck_id), keep)
    room = _room(store, project_id, deck_id)
    (room / SELECTION_FILE).write_text(revised.model_dump_json(indent=2), encoding="utf-8")
    return revised


async def build(
    client: ModelClient, store: ProjectStore, project_id: str, deck_id: str
) -> Path:
    """The words, then the file. An edit that only dropped or reordered costs no model call."""
    chosen = load(store, project_id, deck_id)
    room = _room(store, project_id, deck_id)
    record = room / PLAN_FILE

    wanted = {entry.candidate.id for entry in chosen.chosen}
    written = (
        SlidePlan.model_validate_json(record.read_text(encoding="utf-8"))
        if record.is_file()
        else None
    )

    if written and wanted <= {slide.candidate_id for slide in written.slides}:
        plan = revise(written, chosen)
    else:
        plan = await plan_slides(client, chosen, await _indexed(store, project_id))

    record.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return build_deck(plan, room / DECK_FILE)
