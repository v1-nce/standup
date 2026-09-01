"""The project's deck on disk. Every function here is deterministic; only agent/ calls the model."""

import asyncio
import threading
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from standup.core import index as index_module
from standup.core import selection as selection_module
from standup.core._json import atomic_write, load_json
from standup.core.gather import candidates, validated
from standup.core.models import (
    Deck,
    DeckDesign,
    Index,
    ResourceKind,
    Scope,
    Selection,
    Slide,
    SlidePlan,
    VisualElement,
)
from standup.core.present import build as render_deck
from standup.core.present import order_fault, revise, slide_problems
from standup.core.projects import ProjectStore
from standup.errors import InvalidInput, NotFound

SELECTION_FILE = "selection.json"
PLAN_FILE = "plan.json"
DECK_FILE = "deck.pptx"
# ponytail: the head of a file, which carries its docstring, imports and first definitions. A change
# made at the bottom of a long file is missed; the upgrade is the commit's diff, once history keeps
# more than line counts.
SOURCE_CHARS = 2_000
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

        chosen = load_json(Selection, record.read_text(encoding="utf-8"), "This project's selection")
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
            _put(store, project_id, PLAN_FILE, SlidePlan(design=written.design, slides=kept))
        else:
            (room / PLAN_FILE).unlink()


def load(store: ProjectStore, project_id: str) -> Selection:
    with _LOCKS[project_id]:
        record = _room(store, project_id) / SELECTION_FILE
        if not record.is_file():
            raise NotFound(f"No deck in {project_id} yet")
        return load_json(Selection, record.read_text(encoding="utf-8"), "This project's selection")


def _plan(store: ProjectStore, project_id: str) -> SlidePlan | None:
    record = _room(store, project_id) / PLAN_FILE
    if not record.is_file():
        return None
    return load_json(SlidePlan, record.read_text(encoding="utf-8"), "This project's slide plan")


def _put(store: ProjectStore, project_id: str, name: str, document: Selection | SlidePlan) -> None:
    home = _room(store, project_id)
    home.mkdir(parents=True, exist_ok=True)
    atomic_write(home / name, document.model_dump_json(indent=2))


def read(store: ProjectStore, project_id: str) -> Deck:
    with _LOCKS[project_id]:
        written = _plan(store, project_id)
        return Deck(
            selection=load(store, project_id),
            design=written.design if written else DeckDesign(),
            slides=written.slides if written else None,
        )


def _surviving(store: ProjectStore, project_id: str, chosen: Selection) -> list[Slide]:
    """Slides a re-selection did not invalidate, in their existing written order.

    A slide is written from one candidate's evidence, so it stays true for as long as that candidate
    is still chosen; only one whose candidate dropped out has lost what it was written from. Free
    slides belong to no candidate and always survive. This used to rebuild the order as every
    evidence slide then every free one — the same bug `write` was fixed for above — which threw a
    `keep`-pinned free slide (a title screen) to the back on the next re-select, even though nothing
    it depended on had changed. Filtering the existing order in place, the way `write` preserves a
    slide's position, is what keeps the two from disagreeing again.
    """
    written = _plan(store, project_id)
    if not written:
        return []
    still_chosen = {entry.candidate.id for entry in chosen.chosen}
    return [slide for slide in written.slides if slide.free or slide.candidate_id in still_chosen]


def select(store: ProjectStore, project_id: str, index: Index, request: str, scope: Scope) -> Deck:
    """A new scope re-derives what the deck is about, keeping the slides it did not invalidate.

    This used to delete every slide outright. That made an ordinary "add a slide about X" — which the
    model reasonably answers with `select` — wipe a finished deck and report success, which is what
    "the slides keep resetting" was.
    """
    settled = validated(scope, index)
    chosen = selection_module.choose(
        index, settled, candidates(index, settled), request=request
    )
    with _LOCKS[project_id]:
        previous = _plan(store, project_id)
        design = previous.design if previous else DeckDesign()
        _put(store, project_id, SELECTION_FILE, chosen)
        kept = _surviving(store, project_id, chosen)
        if kept or design != DeckDesign():
            _put(store, project_id, PLAN_FILE, SlidePlan(design=design, slides=kept))
        else:
            (_room(store, project_id) / PLAN_FILE).unlink(missing_ok=True)
    return Deck(selection=chosen, design=design, slides=kept or None)


def edit(store: ProjectStore, project_id: str, keep: list[str]) -> Deck:
    """The keep-list applied literally. Slides follow it for free where they already exist.

    `keep` may name candidate ids and free-slide ids together, interleaved in one order — a free
    slide (a title, a section break) has no place in `Selection`, so `selection_module.edited`
    only ever sees the candidate subset, while `revise` gets the full list to place everything.
    A candidate promoted back from the cut list has no slide yet - that's expected, not a fault,
    so it's left out of what `revise` is asked to place rather than failing the whole `keep` and
    losing every slide already written for the rest.
    """
    with _LOCKS[project_id]:
        current = load(store, project_id)
        candidate_ids = {entry.candidate.id for entry in [*current.chosen, *current.cut]}
        written = _plan(store, project_id)
        written_ids = {slide.candidate_id for slide in (written.slides if written else [])}
        free_ids = {slide.candidate_id for slide in (written.slides if written else []) if slide.free}

        unknown = [item for item in dict.fromkeys(keep) if item not in candidate_ids | free_ids]
        if unknown:
            raise NotFound(f"This deck has nothing called {unknown}")

        placeable = [item for item in keep if item in written_ids]
        followed = revise(written, placeable) if written else None

        chosen = selection_module.edited(current, [item for item in keep if item in candidate_ids])
        _put(store, project_id, SELECTION_FILE, chosen)
        if followed is not None:
            _put(store, project_id, PLAN_FILE, followed)
    return Deck(
        selection=chosen,
        design=followed.design if followed else DeckDesign(),
        slides=followed.slides if followed else None,
    )


def write(
    store: ProjectStore,
    project_id: str,
    index: Index,
    slides: list[Slide],
    design: DeckDesign | None = None,
) -> Deck:
    """Slides merged onto whatever is written, then checked. One fault rejects the whole merge.

    A free slide (`Slide.free`) carries no evidence and is exempt from grounding — it must still
    be unambiguous: not a hallucinated candidate id in disguise, and not claiming to be free when
    it is actually a real candidate. That check covers the cut list too, not just what's chosen —
    a free slide squatting on a cut candidate's id would silently take over that id if the
    candidate were ever restored via `keep`. New free slides land after the evidence slides; where
    they end up staying is `keep`'s job, same as an evidence slide's position - and a slide that is
    already placed, evidence or free, keeps that position across a write that never named it. This
    used to rebuild the whole order as "every evidence slide, then every free one" on every write,
    which silently threw a `keep`-interleaved free slide (a title screen pinned to the front) to the
    back the next time any other slide's text or image changed.
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
        existing_order = [slide.candidate_id for slide in (existing.slides if existing else [])]
        existing_ids = set(existing_order)
        by_id = {slide.candidate_id: slide for slide in (existing.slides if existing else [])}
        by_id.update({slide.candidate_id: slide for slide in slides})

        # A slide already in the plan stays exactly where it is. Only a candidate written for the
        # first time needs a position - it takes the slot `wanted`'s order implies among evidence
        # slides already placed; a free slide written for the first time takes the end.
        order = list(existing_order)
        insert_at = 0
        for candidate_id in wanted:
            if candidate_id in existing_ids:
                insert_at = order.index(candidate_id) + 1
            elif candidate_id in by_id:
                order.insert(insert_at, candidate_id)
                insert_at += 1
        order += [
            s.candidate_id for s in slides
            if s.candidate_id not in existing_ids and s.candidate_id not in wanted_set
        ]
        merged = SlidePlan(
            design=design or (existing.design if existing else DeckDesign()),
            slides=[by_id[item] for item in order if item in by_id],
        )

        faults = slide_problems(slides, index)
        if faults:
            raise InvalidInput("; ".join(faults))

        _put(store, project_id, PLAN_FILE, merged)
    return Deck(selection=chosen, design=merged.design, slides=merged.slides)


def update(
    store: ProjectStore,
    project_id: str,
    index: Index,
    slide_id: str,
    changes: dict[str, object],
    upsert_elements: list[VisualElement] | None = None,
    remove_element_ids: list[str] | None = None,
) -> Deck:
    """Patch one slide and/or its stable canvas layers; omitted state remains unchanged."""
    with _LOCKS[project_id]:
        chosen = load(store, project_id)
        written = _plan(store, project_id)
        if written is None:
            raise NotFound("No slides have been written yet")
        by_id = {slide.candidate_id: slide for slide in written.slides}
        if slide_id not in by_id:
            raise NotFound(f"No slide {slide_id}")
        current = by_id[slide_id]
        upserts = upsert_elements or []
        remove_ids = set(remove_element_ids or [])
        existing_ids = {element.id for element in current.elements}
        unknown = remove_ids - existing_ids
        if unknown:
            raise NotFound(f"No visual elements {sorted(unknown)} on slide {slide_id}")
        by_element = {element.id: element for element in current.elements}
        by_element.update({element.id: element for element in upserts})
        order = [element.id for element in current.elements if element.id not in remove_ids]
        order += [element.id for element in upserts if element.id not in existing_ids]
        if upserts or remove_ids:
            changes["elements"] = [by_element[element_id] for element_id in order]
        revised = Slide.model_validate({**current.model_dump(), **changes})
        faults = slide_problems([revised], index)
        if faults:
            raise InvalidInput("; ".join(faults))
        slides = [revised if slide.candidate_id == slide_id else slide for slide in written.slides]
        plan = SlidePlan(design=written.design, slides=slides)
        _put(store, project_id, PLAN_FILE, plan)
    return Deck(selection=chosen, design=plan.design, slides=plan.slides)


def style(store: ProjectStore, project_id: str, design: DeckDesign) -> Deck:
    """Replace deck-level art direction without regenerating or rewording any slide."""
    with _LOCKS[project_id]:
        chosen = load(store, project_id)
        written = _plan(store, project_id)
        plan = SlidePlan(design=design, slides=written.slides if written else [])
        _put(store, project_id, PLAN_FILE, plan)
    return Deck(selection=chosen, design=design, slides=plan.slides or None)


def render(store: ProjectStore, project_id: str) -> Path:
    with _LOCKS[project_id]:
        written = _plan(store, project_id)
        if not written or not written.slides:
            raise InvalidInput("No slides have been written yet")
        chosen = load(store, project_id)
        if chosen.chosen and not any(not slide.free for slide in written.slides):
            raise InvalidInput("A deck with selected evidence needs evidence slides, not only free slides")
        if order_fault(written.slides, chosen):
            raise InvalidInput("The deck is not complete yet")
        images = _images(store, project_id, written.slides)
        return render_deck(written, _room(store, project_id) / DECK_FILE, images)


def _locate(store: ProjectStore, project_id: str, ids: Iterable[str]) -> dict[str, Path]:
    """Where a resource-prefixed id actually lives on disk. A folder resource's file sits under its
    own root; a lone attached file's `location` already is that file. Ids whose resource is gone are
    left out rather than guessed at."""
    resources = {resource.id: resource for resource in store.get(project_id).resources}
    found: dict[str, Path] = {}
    for item in ids:
        if item in found:
            continue
        resource_id, _, rest = item.partition("/")
        resource = resources.get(resource_id)
        if resource is None:
            continue
        location = Path(resource.location)
        found[item] = location if resource.kind is ResourceKind.FILE else location / rest
    return found


def _images(store: ProjectStore, project_id: str, slides: list[Slide]) -> dict[str, Path]:
    ids = [slide.image for slide in slides if slide.image]
    ids += [
        element.image
        for slide in slides
        for element in slide.elements
        if element.kind == "image" and element.image
    ]
    return _locate(store, project_id, ids)


def sources(store: ProjectStore, project_id: str, ids: Iterable[str]) -> dict[str, str]:
    """What each named file actually says, read fresh from disk rather than stored in the index.

    Storing content would grow the index with the resource, which memory forbids; only a handful of
    candidates are ever chosen, so reading those costs nothing that matters. Anything unreadable or
    no longer there is simply absent — a deleted file is still evidence through its commits.
    """
    found: dict[str, str] = {}
    for item, path in _locate(store, project_id, ids).items():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if text.strip():
            found[item] = text[:SOURCE_CHARS]
    return found
