from datetime import UTC, datetime

from standup.core import agent, pipeline
from standup.core.agent import Turn
from standup.core.agent.commands import Keep, Select, Write, apply
from standup.core.models import ChatMessage, Scope, Slide

TODAY = datetime(2026, 8, 3, tzinfo=UTC)


class StubClient:
    """Returns each turn in order, and keeps every prompt it was given."""

    def __init__(self, *turns: Turn) -> None:
        self.turns = list(turns)
        self.prompts: list[str] = []
        self.system: str | None = None

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.prompts.append(prompt)
        self.system = system
        return self.turns.pop(0)


async def talk(client, store, project_id, *messages):
    history = [ChatMessage(role="user", content=said, at=TODAY) for said in messages]
    return await agent.converse(client, store, project_id, history, today=TODAY)


def test_select_derives_a_deck_and_says_what_still_needs_writing(store, project, index):
    result = apply(
        store,
        project.id,
        index,
        Select(action="select", request="standup", scope=Scope(slide_budget=2)),
    )
    assert "2 chosen" in result
    assert "still to write" in result
    assert len(pipeline.read(store, project.id).selection.chosen) == 2


def test_keep_is_applied_literally(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=2)))
    chosen = [e.candidate.id for e in pipeline.read(store, project.id).selection.chosen]

    apply(store, project.id, index, Keep(action="keep", ids=list(reversed(chosen))))
    assert [
        e.candidate.id for e in pipeline.read(store, project.id).selection.chosen
    ] == list(reversed(chosen))


def test_a_command_the_agent_got_wrong_comes_back_as_text(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=2)))
    result = apply(store, project.id, index, Keep(action="keep", ids=["src/imaginary.py"]))
    assert result.startswith("keep rejected:")


def test_an_ungrounded_slide_is_rejected_with_the_reason(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1)))
    only = pipeline.read(store, project.id).selection.chosen[0].candidate.id

    result = apply(
        store,
        project.id,
        index,
        Write(action="write", slides=[Slide(candidate_id=only, title="T", bullets=["src/ghost.py"])]),
    )
    assert "write rejected" in result
    assert "src/ghost.py" in result


async def test_a_turn_with_no_commands_is_one_call_and_changes_nothing(store, project):
    client = StubClient(Turn(reply="Nothing to do."))
    assert await talk(client, store, project.id, "thanks") == "Nothing to do."
    assert len(client.prompts) == 1


async def test_the_agent_builds_a_deck_then_reports_on_it(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()

    client = StubClient(
        Turn(reply="Looking.", commands=[Select(action="select", request="standup", scope=scope)]),
        Turn(
            reply="Writing.",
            commands=[
                Write(
                    action="write",
                    slides=[Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"])],
                )
            ],
        ),
        Turn(reply="One slide on the router."),
    )

    assert await talk(client, store, project.id, "standup tomorrow") == "One slide on the router."
    assert len(client.prompts) == 3
    assert pipeline.read(store, project.id).slides[0].title == "Router"
    # No .pptx is written during a turn: the file is produced when it is downloaded.
    assert not (store.paths(project.id).deck / pipeline.DECK_FILE).exists()
    assert pipeline.render(store, project.id).is_file()


async def test_a_rejected_write_reaches_the_next_round(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]

    bad = Slide(candidate_id=chosen.candidate.id, title="T", bullets=["src/ghost.py"])
    client = StubClient(
        Turn(reply="Writing.", commands=[Write(action="write", slides=[bad])]),
        Turn(reply="Fixed it."),
    )

    assert await talk(client, store, project.id, "write it") == "Fixed it."
    assert "src/ghost.py" in client.prompts[1]
    assert "write rejected" in client.prompts[1]


async def test_an_agent_that_never_settles_is_asked_to_answer_instead(store, project):
    forever = Turn(reply="still going", commands=[Keep(action="keep", ids=[])])
    client = StubClient(*[forever] * (agent.MAX_ROUNDS - 1), Turn(reply="Here is where it got to."))

    assert await talk(client, store, project.id, "loop forever") == "Here is where it got to."
    assert len(client.prompts) == agent.MAX_ROUNDS
    assert "LAST ROUND" in client.prompts[-1]
    assert "LAST ROUND" not in client.prompts[-2]


async def test_the_last_round_answers_even_if_it_still_wants_to_act(store, project):
    forever = Turn(reply="still going", commands=[Keep(action="keep", ids=[])])
    client = StubClient(*[forever] * agent.MAX_ROUNDS)

    # Commands on the final round are not run — the budget is spent, and the work already
    # applied must not be thrown away with an exception.
    assert await talk(client, store, project.id, "loop forever") == "still going"


async def test_the_agent_is_never_shown_a_score_or_a_signal(store, project, index):
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    client = StubClient(Turn(reply="ok"))
    await talk(client, store, project.id, "what is on it?")

    prompt, system = client.prompts[0], client.system
    for banned in ("score", "churn", "centrality", "emphasis", "affinity"):
        assert banned not in prompt.lower()
        assert banned not in system.lower()
