"""The project's deck on disk. Every function here is deterministic; only agent/ calls the model."""

import asyncio
from pathlib import Path

from standup.core import index as index_module
from standup.core import selection as selection_module
from standup.core.gather import candidates, validated
from standup.core.models import Deck, Index, Scope, Selection, Slide, SlidePlan
from standup.core.present import build as render_deck
from standup.core.present import problems, revise
from standup.core.projects import ProjectStore
from standup.errors import InvalidInput, NotFound

SELECTION_FILE = "selection.json"
PLAN_FILE = "plan.json"
DECK_FILE = "deck.pptx"


def _room(store: ProjectStore, project_id: str) -> Path:
    return store.paths(project_id).deck


async def indexed(store: ProjectStore, project_id: str) -> Index | None:
    """None when nothing is attached: there is nothing to derive facts from."""
    resources = store.get(project_id).resources
    if not resources:
        return None
    return await asyncio.to_thread(_merge, store, project_id)


def _merge(store: ProjectStore, project_id: str) -> Index:
    home = store.paths(project_id).index
    resources = store.get(project_id).resources
    for resource in resources:
        if not Path(resource.location).exists():
            raise InvalidInput(f"{resource.name} is no longer at {resource.location}")
    return index_module.merged(
        (resource.id, index_module.ensure(Path(resource.location), home / resource.id))
        for resource in resources
    )


def forget(store: ProjectStore, project_id: str, resource_id: str) -> None:
    """A detached resource takes the deck it produced with it.

    Every candidate id begins with the resource it came from, so the prefix is the whole test.
    Without this the deck keeps citing files nothing can index, and the agent reads those ids back
    as context that still exists.
    """
    room = _room(store, project_id)
    record = room / SELECTION_FILE
    if not record.is_file():
        return

    gone = f"{resource_id}/"
    (room / DECK_FILE).unlink(missing_ok=True)  # rendered on download; never a copy left behind

    chosen = Selection.model_validate_json(record.read_text(encoding="utf-8"))
    held = chosen.model_copy(
        update={
            "chosen": [item for item in chosen.chosen if not item.candidate.id.startswith(gone)],
            "cut": [item for item in chosen.cut if not item.candidate.id.startswith(gone)],
        }
    )
    if not held.chosen and not held.cut:
        record.unlink()
        (room / PLAN_FILE).unlink(missing_ok=True)
        return
    _put(store, project_id, SELECTION_FILE, held)

    written = _plan(store, project_id)
    if not written:
        return
    kept = [slide for slide in written.slides if not slide.candidate_id.startswith(gone)]
    if kept:
        _put(store, project_id, PLAN_FILE, SlidePlan(slides=kept))
    else:
        (room / PLAN_FILE).unlink()


def load(store: ProjectStore, project_id: str) -> Selection:
    record = _room(store, project_id) / SELECTION_FILE
    if not record.is_file():
        raise NotFound(f"No deck in {project_id} yet")
    return Selection.model_validate_json(record.read_text(encoding="utf-8"))


def _plan(store: ProjectStore, project_id: str) -> SlidePlan | None:
    record = _room(store, project_id) / PLAN_FILE
    if not record.is_file():
        return None
    return SlidePlan.model_validate_json(record.read_text(encoding="utf-8"))


def _put(store: ProjectStore, project_id: str, name: str, document: Selection | SlidePlan) -> None:
    home = _room(store, project_id)
    home.mkdir(parents=True, exist_ok=True)
    (home / name).write_text(document.model_dump_json(indent=2), encoding="utf-8")


def read(store: ProjectStore, project_id: str) -> Deck:
    written = _plan(store, project_id)
    return Deck(selection=load(store, project_id), slides=written.slides if written else None)


def select(store: ProjectStore, project_id: str, index: Index, request: str, scope: Scope) -> Deck:
    """A new scope replaces the deck. Slides written against the old one no longer apply."""
    settled = validated(scope, index)
    chosen = selection_module.choose(
        index, settled, candidates(index, settled), request=request
    )
    _put(store, project_id, SELECTION_FILE, chosen)
    (_room(store, project_id) / PLAN_FILE).unlink(missing_ok=True)
    return Deck(selection=chosen)


def edit(store: ProjectStore, project_id: str, keep: list[str]) -> Deck:
    """The keep-list applied literally. Slides follow it for free where they already exist."""
    chosen = selection_module.edited(load(store, project_id), keep)
    _put(store, project_id, SELECTION_FILE, chosen)

    written = _plan(store, project_id)
    try:
        followed = revise(written, chosen) if written else None
    except InvalidInput:
        (_room(store, project_id) / PLAN_FILE).unlink(missing_ok=True)
        return Deck(selection=chosen)

    if followed:
        _put(store, project_id, PLAN_FILE, followed)
    return Deck(selection=chosen, slides=followed.slides if followed else None)


def write(store: ProjectStore, project_id: str, index: Index, slides: list[Slide]) -> Deck:
    """Slides merged onto whatever is written, then checked. One fault rejects the whole merge."""
    chosen = load(store, project_id)
    existing = _plan(store, project_id)
    by_id = {slide.candidate_id: slide for slide in (existing.slides if existing else [])}
    by_id.update({slide.candidate_id: slide for slide in slides})

    wanted = [entry.candidate.id for entry in chosen.chosen]
    merged = SlidePlan(slides=[by_id[item] for item in wanted if item in by_id])

    faults = problems(merged, chosen, index)
    if faults:
        raise InvalidInput("; ".join(faults))

    _put(store, project_id, PLAN_FILE, merged)
    return Deck(selection=chosen, slides=merged.slides)


def render(store: ProjectStore, project_id: str) -> Path:
    written = _plan(store, project_id)
    if not written:
        raise InvalidInput("No slides have been written yet")
    return render_deck(written, _room(store, project_id) / DECK_FILE)
