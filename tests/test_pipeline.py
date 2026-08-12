from datetime import UTC, datetime

import pytest

from standup.core import pipeline
from standup.core.gather import candidates
from standup.core.models import Scope, Slide
from standup.core.selection import choose
from standup.errors import InvalidInput, NotFound
from tests.conftest import pdf_saying


def slides_for(deck) -> list[Slide]:
    return [
        Slide(candidate_id=entry.candidate.id, title="A slide", bullets=["one"])
        for entry in deck.selection.chosen
    ]


def test_selecting_writes_a_deck_you_can_read_back(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup tomorrow", Scope(slide_budget=2))

    assert (store.paths(project.id).deck / pipeline.SELECTION_FILE).is_file()
    assert pipeline.read(store, project.id) == deck
    assert len(deck.selection.chosen) == 2
    assert deck.slides is None
    assert all(entry.signals for entry in deck.selection.chosen)


def test_selecting_chooses_what_choose_would_have(store, project, index):
    scope = Scope(slide_budget=2)
    deck = pipeline.select(store, project.id, index, "standup", scope)
    direct = choose(index, scope, candidates(index, scope), request="standup")
    assert [e.candidate.id for e in deck.selection.chosen] == [
        e.candidate.id for e in direct.chosen
    ]


def test_a_second_select_replaces_the_deck_and_its_slides(store, project, index):
    first = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    pipeline.write(store, project.id, index, slides_for(first))

    replaced = pipeline.select(store, project.id, index, "something else", Scope(slide_budget=2))
    assert replaced.selection.request == "something else"
    assert pipeline.read(store, project.id).slides is None


def test_an_edit_is_obeyed_literally(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    backwards = [entry.candidate.id for entry in reversed(deck.selection.chosen)]

    revised = pipeline.edit(store, project.id, backwards)
    assert [e.candidate.id for e in revised.selection.chosen] == backwards
    assert pipeline.read(store, project.id) == revised

    kept = backwards[:1]
    trimmed = pipeline.edit(store, project.id, kept)
    assert [e.candidate.id for e in trimmed.selection.chosen] == kept
    assert backwards[1] in {e.candidate.id for e in trimmed.selection.cut}


def test_naming_the_same_item_twice_asks_for_it_once(store, project, index):
    """Repeats used to survive as duplicate entries, then render as one block copied per slide."""
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    twice = deck.selection.chosen[0].candidate.id

    revised = pipeline.edit(store, project.id, [twice, twice, twice])
    assert [entry.candidate.id for entry in revised.selection.chosen] == [twice]

    written = pipeline.write(store, project.id, index, slides_for(revised))
    assert [slide.candidate_id for slide in written.slides] == [twice]


def test_editing_to_something_that_was_never_a_candidate_is_refused(store, project, index):
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    with pytest.raises(NotFound):
        pipeline.edit(store, project.id, ["src/imaginary.py"])


def test_writing_slides_that_match_the_selection_is_accepted(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    written = pipeline.write(store, project.id, index, slides_for(deck))

    assert (store.paths(project.id).deck / pipeline.PLAN_FILE).is_file()
    assert [s.candidate_id for s in written.slides] == [
        e.candidate.id for e in deck.selection.chosen
    ]


def test_writing_a_slide_for_something_not_chosen_is_refused(store, project, index):
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=1))
    bogus = Slide(candidate_id="src/imaginary.py", title="Ghost", bullets=["x"])

    with pytest.raises(NotFound, match="src/imaginary.py"):
        pipeline.write(store, project.id, index, [bogus])
    assert not (store.paths(project.id).deck / pipeline.PLAN_FILE).is_file()


def test_rendering_an_empty_plan_is_refused_rather_than_producing_an_empty_deck(store, project, index):
    """A SlidePlan(slides=[]) is truthy as a Pydantic model — render() must check its content."""
    future = datetime(2099, 1, 1, tzinfo=UTC)
    empty = pipeline.select(store, project.id, index, "nothing here", Scope(since=future, slide_budget=1))
    assert empty.selection.chosen == []

    pipeline.write(store, project.id, index, [])
    with pytest.raises(InvalidInput, match="No slides"):
        pipeline.render(store, project.id)


def test_a_slide_naming_something_that_does_not_exist_is_rejected(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    drafted = slides_for(deck)
    drafted[0].bullets = ["Rewrote src/imaginary.py"]

    with pytest.raises(InvalidInput, match="no file 'src/imaginary.py'"):
        pipeline.write(store, project.id, index, drafted)
    assert not (store.paths(project.id).deck / pipeline.PLAN_FILE).is_file()


async def test_detaching_a_resource_takes_the_deck_it_produced_with_it(store, project):
    """Left behind, its ids reach the agent as evidence and read as context that still exists."""
    paper = store.attach_file(project.id, "notes.pdf", pdf_saying("Router notes"))
    both = await pipeline.indexed(store, project.id)
    deck = pipeline.select(store, project.id, both, "everything", Scope(slide_budget=5))
    pipeline.write(store, project.id, both, slides_for(deck))
    assert any(entry.candidate.id.startswith(paper.id) for entry in deck.selection.chosen)

    store.detach(project.id, paper.id)
    pipeline.forget(store, project.id, paper.id)

    left = pipeline.read(store, project.id)
    named = [entry.candidate.id for entry in [*left.selection.chosen, *left.selection.cut]]
    assert named and not any(item.startswith(paper.id) for item in named)
    assert not any(slide.candidate_id.startswith(paper.id) for slide in left.slides or [])
    assert not (store.paths(project.id).deck / pipeline.DECK_FILE).is_file()


def test_detaching_the_last_resource_leaves_no_deck_at_all(store, project, resource_id, index):
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))

    store.detach(project.id, resource_id)
    pipeline.forget(store, project.id, resource_id)

    with pytest.raises(NotFound):
        pipeline.read(store, project.id)


def test_rewriting_one_slide_leaves_the_others_untouched(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    pipeline.write(store, project.id, index, slides_for(deck))
    before = pipeline.read(store, project.id).slides

    reworded = Slide(candidate_id=before[0].candidate_id, title="Reworded", bullets=["new"])
    after = pipeline.write(store, project.id, index, [reworded])

    assert after.slides[0] == reworded
    assert after.slides[1:] == before[1:]


def test_reordering_carries_the_slides_with_it(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    pipeline.write(store, project.id, index, slides_for(deck))

    backwards = [entry.candidate.id for entry in reversed(deck.selection.chosen)]
    reordered = pipeline.edit(store, project.id, backwards)
    assert [s.candidate_id for s in reordered.slides] == backwards


def test_promoting_a_cut_item_leaves_it_needing_a_slide(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=1))
    pipeline.write(store, project.id, index, slides_for(deck))

    everything = [e.candidate.id for e in [*deck.selection.chosen, *deck.selection.cut]]
    promoted = pipeline.edit(store, project.id, everything)
    assert promoted.slides is None


def test_rendering_needs_slides_first(store, project, index):
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    with pytest.raises(InvalidInput, match="No slides"):
        pipeline.render(store, project.id)


def test_rendering_writes_a_deck_file(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    pipeline.write(store, project.id, index, slides_for(deck))
    assert pipeline.render(store, project.id).is_file()


def test_a_project_with_no_deck_yet_is_not_found(store, project):
    with pytest.raises(NotFound):
        pipeline.read(store, project.id)
