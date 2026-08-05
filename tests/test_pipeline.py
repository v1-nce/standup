import subprocess
from datetime import UTC, datetime

import pytest

from standup.core import pipeline
from standup.core.models import Scope, Slide, SlidePlan
from standup.core.projects import ProjectStore
from standup.core.selection import choose
from standup.errors import NotFound

TODAY = datetime(2026, 8, 3, tzinfo=UTC)


class StubClient:
    """Answers the scope call, then the plan call, and counts how often it was needed."""

    def __init__(self) -> None:
        self.calls = 0

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.calls += 1
        if schema is Scope:
            return Scope(slide_budget=2)
        return SlidePlan(
            slides=[
                Slide(candidate_id=line.removeprefix("id: "), title="A slide", bullets=["one"])
                for line in prompt.splitlines()
                if line.startswith("id: ")
            ]
        )


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(store, tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "hub.py").write_text("class Router:\n    pass\n")
    (repo / "src" / "leaf.py").write_text("def alone():\n    pass\n")
    (repo / "README.md").write_text("The Router matters here.\n")
    for command in (
        ["init", "-q"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "Tester"],
        ["add", "-A"],
        ["commit", "-qm", "first commit"],
    ):
        subprocess.run(["git", "-C", str(repo), *command], check=True, capture_output=True)
    return store.create("Demo", str(repo))


async def test_proposing_writes_a_selection_you_can_read_back(store, project):
    client = StubClient()
    deck_id, proposed = await pipeline.propose(
        client, store, project.id, "standup tomorrow", slide_budget=2, today=TODAY
    )

    assert (store.paths(project.id).decks / deck_id / pipeline.SELECTION_FILE).is_file()
    assert pipeline.load(store, project.id, deck_id) == proposed
    assert len(proposed.chosen) == 2
    assert all(entry.signals for entry in proposed.chosen)


async def test_the_same_request_on_an_unchanged_repo_is_the_same_deck(store, project):
    first, _ = await pipeline.propose(
        StubClient(), store, project.id, "standup", slide_budget=2, today=TODAY
    )
    second, _ = await pipeline.propose(
        StubClient(), store, project.id, "standup", slide_budget=2, today=TODAY
    )
    third, _ = await pipeline.propose(
        StubClient(), store, project.id, "something else", slide_budget=2, today=TODAY
    )
    assert first == second != third


async def test_the_pipeline_chooses_what_choose_would_have(store, project):
    client = StubClient()
    _, proposed = await pipeline.propose(
        client, store, project.id, "standup", slide_budget=2, today=TODAY
    )

    from standup.core import index as index_module
    from standup.core.gather import candidates

    built = index_module.build(store.working_tree(project.id))
    scope = Scope(slide_budget=2)
    direct = choose(built, scope, candidates(built, scope), request="standup")
    assert [e.candidate.id for e in proposed.chosen] == [e.candidate.id for e in direct.chosen]


async def test_an_edit_is_obeyed_literally(store, project):
    deck_id, proposed = await pipeline.propose(
        StubClient(), store, project.id, "standup", slide_budget=2, today=TODAY
    )
    backwards = [entry.candidate.id for entry in reversed(proposed.chosen)]

    revised = pipeline.edit(store, project.id, deck_id, backwards)
    assert [e.candidate.id for e in revised.chosen] == backwards
    assert pipeline.load(store, project.id, deck_id) == revised

    kept = backwards[:1]
    trimmed = pipeline.edit(store, project.id, deck_id, kept)
    assert [e.candidate.id for e in trimmed.chosen] == kept
    assert backwards[1] in {e.candidate.id for e in trimmed.cut}


async def test_editing_to_something_that_was_never_a_candidate_is_refused(store, project):
    deck_id, _ = await pipeline.propose(
        StubClient(), store, project.id, "standup", slide_budget=2, today=TODAY
    )
    with pytest.raises(NotFound):
        pipeline.edit(store, project.id, deck_id, ["src/imaginary.py"])


async def test_building_produces_a_deck_and_a_plan(store, project):
    client = StubClient()
    deck_id, _ = await pipeline.propose(
        client, store, project.id, "standup", slide_budget=2, today=TODAY
    )
    written = await pipeline.build(client, store, project.id, deck_id)

    assert written.is_file()
    assert (written.parent / pipeline.PLAN_FILE).is_file()
    assert client.calls == 2


async def test_rebuilding_after_a_reorder_costs_no_model_call(store, project):
    client = StubClient()
    deck_id, proposed = await pipeline.propose(
        client, store, project.id, "standup", slide_budget=2, today=TODAY
    )
    await pipeline.build(client, store, project.id, deck_id)
    spent = client.calls

    backwards = [entry.candidate.id for entry in reversed(proposed.chosen)]
    pipeline.edit(store, project.id, deck_id, backwards)
    await pipeline.build(client, store, project.id, deck_id)

    assert client.calls == spent
    written = SlidePlan.model_validate_json(
        (store.paths(project.id).decks / deck_id / pipeline.PLAN_FILE).read_text(encoding="utf-8")
    )
    assert [slide.candidate_id for slide in written.slides] == backwards


async def test_restoring_a_cut_item_does_need_the_model_again(store, project):
    client = StubClient()
    deck_id, proposed = await pipeline.propose(
        client, store, project.id, "standup", slide_budget=1, today=TODAY
    )
    await pipeline.build(client, store, project.id, deck_id)
    spent = client.calls

    everything = [e.candidate.id for e in [*proposed.chosen, *proposed.cut]]
    pipeline.edit(store, project.id, deck_id, everything)
    await pipeline.build(client, store, project.id, deck_id)

    assert client.calls == spent + 1


def test_an_unknown_deck_is_not_found(store, project):
    with pytest.raises(NotFound):
        pipeline.load(store, project.id, "nosuchid")
