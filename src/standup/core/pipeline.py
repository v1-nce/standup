"""The project's deck on disk. Every function here is deterministic; only agent/ calls the model."""

import asyncio
import threading
from collections import defaultdict
from pathlib import Path

from standup.core import index as index_module
from standup.core import selection as selection_module
from standup.core.gather import candidates, validated
from standup.core.models import Deck, Index, Scope, Selection, Slide, SlidePlan
from standup.core.present import build as render_deck
from standup.core.present import revise, slide_problems
from standup.core.projects import ProjectStore
from standup.errors import InvalidInput, NotFound

SELECTION_FILE = "selection.json"
PLAN_FILE = "plan.json"
DECK_FILE = "deck.pptx"
_LOCKS: defaultdict[str, threading.RLock] = defaultdict(threading.RLock)
_INDEX_CACHE: dict[str, tuple[str, Index]] = {}
_INDEX_CACHE_MAX = 16


def evict(project_id: str) -> None:
    """Drop a deleted project's in-memory bookkeeping — the lock and any cached merge."""
    _LOCKS.pop(project_id, None)
    _INDEX_CACHE.pop(project_id, None)


def _room(store: ProjectStore, project_id: str) -> Path:
    return store.paths(project_id).deck


async def indexed(store: ProjectStore, project_id: str) -> Index | None:
    """None when nothing is attached: there is nothing to derive facts from."""
    resources = store.get(project_id).resources
    if not resources:
        return None
    return await asyncio.to_thread(_merge, store, project_id)


def _merge(store: ProjectStore, project_id: str) -> Index:
    """`ensure` is cheap and runs every call; the expensive part — `merged`'s PageRank and
    doc-emphasis pass — only reruns when a resource's fingerprint actually changed."""
    home = store.paths(project_id).index
    resources = store.get(project_id).resources
    for resource in resources:
        if not Path(resource.location).exists():
            raise InvalidInput(f"{resource.name} is no longer at {resource.location}")

    facts = [
        (resource.id, index_module.ensure(Path(resource.location), home / resource.id))
        for resource in resources
    ]
    key = "|".join(sorted(f"{rid}:{part.fingerprint}" for rid, part in facts))

    cached = _INDEX_CACHE.get(project_id)
    if cached and cached[0] == key:
        return cached[1]

    merged = index_module.merged(facts)
    if project_id not in _INDEX_CACHE and len(_INDEX_CACHE) >= _INDEX_CACHE_MAX:
        _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
    _INDEX_CACHE[project_id] = (key, merged)
    return merged


def forget(store: ProjectStore, project_id: str, resource_id: str) -> None:
    """A detached resource takes the deck it produced with it.

    Every candidate id begins with the resource it came from, so the prefix is the whole test.
    Without this the deck keeps citing files nothing can index, and the agent reads those ids back
    as context that still exists.
    """
    with _LOCKS[project_id]:
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
    with _LOCKS[project_id]:
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
    with _LOCKS[project_id]:
        written = _plan(store, project_id)
        return Deck(selection=load(store, project_id), slides=written.slides if written else None)


def select(store: ProjectStore, project_id: str, index: Index, request: str, scope: Scope) -> Deck:
    """A new scope replaces the deck. Slides written against the old one no longer apply."""
    settled = validated(scope, index)
    chosen = selection_module.choose(
        index, settled, candidates(index, settled), request=request
    )
    with _LOCKS[project_id]:
        _put(store, project_id, SELECTION_FILE, chosen)
        (_room(store, project_id) / PLAN_FILE).unlink(missing_ok=True)
    return Deck(selection=chosen)


def edit(store: ProjectStore, project_id: str, keep: list[str]) -> Deck:
    """The keep-list applied literally. Slides follow it for free where they already exist.

    `keep` may name candidate ids and free-slide ids together, interleaved in one order — a free
    slide (a title, a section break) has no place in `Selection`, so `selection_module.edited`
    only ever sees the candidate subset, while `revise` gets the full list to place everything.
    """
    with _LOCKS[project_id]:
        current = load(store, project_id)
        candidate_ids = {entry.candidate.id for entry in [*current.chosen, *current.cut]}
        written = _plan(store, project_id)
        free_ids = {slide.candidate_id for slide in (written.slides if written else []) if slide.free}

        unknown = [item for item in dict.fromkeys(keep) if item not in candidate_ids | free_ids]
        if unknown:
            raise NotFound(f"This deck has nothing called {unknown}")

        chosen = selection_module.edited(current, [item for item in keep if item in candidate_ids])
        _put(store, project_id, SELECTION_FILE, chosen)

        try:
            followed = revise(written, keep) if written else None
        except InvalidInput:
            (_room(store, project_id) / PLAN_FILE).unlink(missing_ok=True)
            return Deck(selection=chosen)

        if followed:
            _put(store, project_id, PLAN_FILE, followed)
    return Deck(selection=chosen, slides=followed.slides if followed else None)


def write(store: ProjectStore, project_id: str, index: Index, slides: list[Slide]) -> Deck:
    """Slides merged onto whatever is written, then checked. One fault rejects the whole merge.

    A free slide (`Slide.free`) carries no evidence and is exempt from grounding — it must still
    be unambiguous: not a hallucinated candidate id in disguise, and not claiming to be free when
    it is actually a real candidate. That check covers the cut list too, not just what's chosen —
    a free slide squatting on a cut candidate's id would silently take over that id if the
    candidate were ever restored via `keep`. New free slides land after the evidence slides; where
    they end up staying is `keep`'s job, same as an evidence slide's position.
    """
    with _LOCKS[project_id]:
        chosen = load(store, project_id)
        wanted = [entry.candidate.id for entry in chosen.chosen]
        wanted_set = set(wanted)
        all_candidates = wanted_set | {entry.candidate.id for entry in chosen.cut}

        stray = [s.candidate_id for s in slides if not s.free and s.candidate_id not in wanted_set]
        if stray:
            raise NotFound(f"Not in this selection: {stray}")
        claimed = [s.candidate_id for s in slides if s.free and s.candidate_id in all_candidates]
        if claimed:
            raise InvalidInput(f"Already a candidate in this selection, cannot be free: {claimed}")

        existing = _plan(store, project_id)
        by_id = {slide.candidate_id: slide for slide in (existing.slides if existing else [])}
        by_id.update({slide.candidate_id: slide for slide in slides})

        order = wanted + [cid for cid in by_id if cid not in wanted_set]
        merged = SlidePlan(slides=[by_id[item] for item in order if item in by_id])

        faults = slide_problems(slides, chosen, index)
        if faults:
            raise InvalidInput("; ".join(faults))

        _put(store, project_id, PLAN_FILE, merged)
    return Deck(selection=chosen, slides=merged.slides)


def render(store: ProjectStore, project_id: str) -> Path:
    with _LOCKS[project_id]:
        written = _plan(store, project_id)
        if not written or not written.slides:
            raise InvalidInput("No slides have been written yet")
        expected = [entry.candidate.id for entry in load(store, project_id).chosen]
        actual = [slide.candidate_id for slide in written.slides if not slide.free]
        if actual != expected:
            raise InvalidInput("The deck is not complete yet")
        return render_deck(written, _room(store, project_id) / DECK_FILE)
