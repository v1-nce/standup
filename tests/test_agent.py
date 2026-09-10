import asyncio
import re
import time
from datetime import UTC, datetime

import pytest

from standup.core import agent, pipeline
from standup.core.agent import Turn
from standup.core.agent.commands import Keep, Select, Style, Update, Write, apply
from standup.core.models import (
    ChatMessage,
    Deck,
    DeckDesign,
    FileFacts,
    Index,
    Scope,
    Selection,
    Slide,
    VisualElement,
)
from standup.core.projects import ChatLog
from standup.errors import NotFound

TODAY = datetime(2026, 8, 3, tzinfo=UTC)


class StubClient:
    """Returns each turn in order, and keeps every prompt it was given."""

    def __init__(self, *turns: Turn) -> None:
        self.turns = list(turns)
        self.prompts: list[str] = []
        self.described: list[str] = []
        self.system: str | None = None

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.prompts.append(prompt)
        self.system = system
        return self.turns.pop(0)

    async def describe_image(self, data, media_type, *, prompt, max_tokens=None):
        self.described.append(media_type)
        return "The deck is readable but the third slide is dense."


async def talk(client, store, project_id, *messages):
    history = [ChatMessage(role="user", content=said, at=TODAY) for said in messages]
    return await agent.converse(client, store, project_id, history, today=TODAY)


def paint(slide: Slide) -> Slide:
    """Give command-level slide fixtures the canvas every newly authored slide requires."""
    if slide.elements:
        return slide
    return slide.model_copy(
        update={
            "elements": [
                VisualElement(
                    id="title",
                    kind="text",
                    x=8,
                    y=12,
                    width=84,
                    height=24,
                    text=slide.title,
                    font_size=36,
                    font_weight="bold",
                )
            ]
        }
    )


def test_a_working_turn_may_omit_reply():
    # A turn that is only commands + notes is a working round; `reply` must default to "", not be
    # required — a model that omits it (Gemini did exactly this) must not fail validation.
    turn = Turn(
        notes="Keeping the router; the leaf is out.",
        commands=[Select(action="select", request="standup", scope=Scope(slide_budget=1))],
    )
    assert turn.reply == ""
    assert turn.notes == "Keeping the router; the leaf is out."


def test_select_derives_a_shortlist_and_says_what_still_needs_writing(store, project, index):
    result = apply(
        store,
        project.id,
        index,
        Select(action="select", request="standup", scope=Scope(slide_budget=2)),
    )
    # budget 2 x overscan 3 = 6, but the fixture has only 2 code files - README.md is prose, so it
    # never becomes a slide candidate - so the whole code set is the shortlist.
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


async def test_prior_keeps_surface_as_preferences_in_the_prompt(store, project, index):
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=1))
    kept = deck.selection.chosen[0].candidate.id
    pipeline.edit(store, project.id, [kept])

    client = StubClient(Turn(reply="Done.", changes_deck=False))
    await talk(client, store, project.id, "make it again")

    assert "PREFERENCES" in client.prompts[0]
    assert f"kept: {kept}" in client.prompts[0]


def test_update_changes_only_named_slide_fields(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1)))
    slide_id = pipeline.read(store, project.id).selection.chosen[0].candidate.id
    original = Slide(candidate_id=slide_id, title="Original", bullets=["Grounded detail"])
    apply(store, project.id, index, Write(action="write", slides=[paint(original)]))

    result = apply(
        store,
        project.id,
        index,
        Update(
            action="update",
            slide_id=slide_id,
            title="Stronger point",
            layout="statement",
            speaker_notes="Explain the trade-off.",
        ),
    )

    revised = pipeline.read(store, project.id).slides[0]
    assert "update(" in result and "rejected" not in result
    assert revised.title == "Stronger point"
    assert revised.bullets == original.bullets
    assert revised.layout == "statement"
    assert revised.speaker_notes == "Explain the trade-off."


def test_update_edits_stable_canvas_layers_without_replacing_the_slide(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1)))
    slide_id = pipeline.read(store, project.id).selection.chosen[0].candidate.id
    title = VisualElement(
        id="title", kind="text", x=8, y=10, width=70, height=20, text="Original", font_size=42
    )
    rule = VisualElement(
        id="rule", kind="line", x=8, y=35, width=40, height=0, stroke="accent", stroke_width=2
    )
    apply(
        store,
        project.id,
        index,
        Write(action="write", slides=[Slide(candidate_id=slide_id, title="Original", elements=[title, rule])]),
    )

    result = apply(
        store,
        project.id,
        index,
        Update(
            action="update",
            slide_id=slide_id,
            upsert_elements=[title.model_copy(update={"text": "Composed"})],
            remove_element_ids=["rule"],
        ),
    )

    revised = pipeline.read(store, project.id).slides[0]
    assert "rejected" not in result
    assert revised.title == "Original"
    assert [(element.id, element.text) for element in revised.elements] == [("title", "Composed")]


def test_style_changes_art_direction_without_rewriting_slides(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1)))
    slide_id = pipeline.read(store, project.id).selection.chosen[0].candidate.id
    original = Slide(candidate_id=slide_id, title="Auth", bullets=["Grounded detail"])
    apply(store, project.id, index, Write(action="write", slides=[paint(original)]))

    design = DeckDesign(theme="dark", accent="#00D4AA", heading_font="Aptos Display")
    result = apply(store, project.id, index, Style(action="style", design=design))
    deck = pipeline.read(store, project.id)

    assert result.startswith("style('dark')") and "rejected" not in result
    assert deck.design == design
    assert deck.slides == [paint(original)]


def test_write_can_land_design_with_new_slides_in_one_operation(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1)))
    slide_id = pipeline.read(store, project.id).selection.chosen[0].candidate.id
    design = DeckDesign(theme="editorial")

    apply(
        store,
        project.id,
        index,
        Write(
            action="write",
            design=design,
            slides=[paint(Slide(candidate_id=slide_id, title="Decision", layout="two_column"))],
        ),
    )

    deck = pipeline.read(store, project.id)
    assert deck.design == design
    assert deck.slides[0].layout == "two_column"


def test_a_command_the_agent_got_wrong_comes_back_as_text(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=2)))
    result = apply(store, project.id, index, Keep(action="keep", ids=["src/imaginary.py"]))
    assert result.startswith("keep(") and " rejected:" in result


def test_an_unexpected_failure_in_apply_comes_back_as_text_not_a_crash(store, project, index, monkeypatch):
    """`apply`'s catch-all was already correct by its own comment - only its test was missing. Every
    other simulated failure in this file raises `InvalidInput`/`NotFound`, caught by the narrower
    branch above it, so nothing drove a genuinely unexpected exception through this one."""
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "select", boom)
    result = apply(
        store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1))
    )
    assert result == "select(budget=1, request='s') rejected: RuntimeError: boom"


def test_a_content_only_slide_composes_without_hand_placed_elements(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1)))
    slide_id = pipeline.read(store, project.id).selection.chosen[0].candidate.id

    result = apply(
        store,
        project.id,
        index,
        Write(
            action="write",
            slides=[Slide(candidate_id=slide_id, title="Template fallback", bullets=["a"])],
        ),
    )

    assert "rejected" not in result
    written = pipeline.read(store, project.id).slides
    assert written[0].title == "Template fallback"
    assert written[0].elements == []


def test_write_is_blocked_until_the_shortlist_is_cut(store, project, index):
    # select leaves an uncut shortlist (budget 1 x overscan 3 = 2 candidates here); writing before
    # keep is the failure the agent produced, so the loop rejects it with keep guidance.
    deck = pipeline.select(store, project.id, index, "s", Scope(slide_budget=1), overscan=3)
    blocked = agent._write_blocker(deck, Write(action="write", slides=[]))
    assert blocked is not None and "cut to 1 with keep" in blocked

    pipeline.edit(store, project.id, [deck.selection.chosen[0].candidate.id])
    cut = pipeline.read(store, project.id)
    assert agent._write_blocker(cut, Write(action="write", slides=[])) is None


def test_an_ungrounded_slide_is_rejected_with_the_reason(store, project, index):
    apply(store, project.id, index, Select(action="select", request="s", scope=Scope(slide_budget=1)))
    only = pipeline.read(store, project.id).selection.chosen[0].candidate.id

    result = apply(
        store,
        project.id,
        index,
        Write(
            action="write",
            slides=[paint(Slide(candidate_id=only, title="T", bullets=["src/ghost.py"]))],
        ),
    )
    assert "write(" in result and " rejected:" in result
    assert "src/ghost.py" in result


async def test_ordinary_chat_uses_one_call(store, project):
    client = StubClient(Turn(reply="Nothing to do.", changes_deck=False))
    assert await talk(client, store, project.id, "thanks") == "Nothing to do."
    assert len(client.prompts) == 1


async def test_a_turn_can_answer_from_an_attached_file_before_a_deck_exists(store, monkeypatch):
    made = store.create("Images")
    described = Index(
        fingerprint="i",
        built_at=TODAY,
        files=[
            FileFacts(
                path="spike-png/spike.png",
                content_hash="h",
                excerpt="A chart with a sharp spike near the end.",
            )
        ],
    )
    async def indexed(store, project_id):
        return described

    monkeypatch.setattr(agent.pipeline, "indexed", indexed)

    client = StubClient(Turn(reply="It shows a chart with a sharp spike near the end."))
    await talk(client, store, made.id, "what is in spike.png?")

    assert "spike-png/spike.png" in client.prompts[0]
    assert "sharp spike near the end" in client.prompts[0]


async def test_indexed_context_is_relevant_to_the_question(store, monkeypatch):
    made = store.create("Docs")
    described = Index(
        fingerprint="i",
        built_at=TODAY,
        files=[
            FileFacts(
                path="resume-pdf/resume.pdf",
                content_hash="r",
                excerpt="Vincent works on backend systems.",
            ),
            FileFacts(
                path="spike-png/spike.png",
                content_hash="s",
                excerpt="A chart with a sharp spike near the end.",
            ),
        ],
    )

    async def indexed(store, project_id):
        return described

    monkeypatch.setattr(agent.pipeline, "indexed", indexed)

    client = StubClient(Turn(reply="It shows a chart with a sharp spike near the end."))
    await talk(client, store, made.id, "what is in spike.png?")

    assert "spike-png/spike.png" in client.prompts[0]
    assert "resume-pdf/resume.pdf" not in client.prompts[0]


async def test_the_system_distinguishes_chat_from_deck_changes(store, project):
    client = StubClient(Turn(reply="Sure."))
    await talk(client, store, project.id, "what files are attached?")

    assert "For ordinary questions about the project or attached context, answer directly with no commands" in client.system
    assert "folder: repo" in client.prompts[0]


async def test_a_successful_build_uses_four_calls(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()

    client = StubClient(
        Turn(
            reply="Looking.",
            changes_deck=True,
            commands=[Select(action="select", request="standup", scope=scope)],
        ),
        Turn(
            reply="Cutting.",
            changes_deck=True,
            commands=[Keep(action="keep", ids=[chosen.candidate.id])],
        ),
        Turn(
            reply="Writing.",
            changes_deck=True,
            commands=[
                Write(
                    action="write",
                    slides=[paint(Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"]))],
                )
            ],
        ),
        Turn(reply="One slide on the router."),
    )

    assert await talk(client, store, project.id, "standup tomorrow") == "One slide on the router."
    assert len(client.prompts) == 4
    assert pipeline.read(store, project.id).slides[0].title == "Router"
    # No .pptx is written during a turn: the file is produced when it is downloaded.
    assert not (store.paths(project.id).deck / pipeline.DECK_FILE).exists()
    assert pipeline.render(store, project.id).is_file()


async def test_a_complete_deck_is_reviewed_visually(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()

    client = StubClient(
        Turn(reply="", changes_deck=True, commands=[Select(action="select", request="standup", scope=scope)]),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=[chosen.candidate.id])]),
        Turn(
            reply="",
            changes_deck=True,
            commands=[
                Write(
                    action="write",
                    slides=[paint(Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"]))],
                )
            ],
        ),
        Turn(reply="Done."),
    )

    await talk(client, store, project.id, "standup tomorrow")
    assert client.described == ["image/png"]
    assert "VISUAL REVIEW" in client.prompts[-1]


async def test_working_notes_carry_to_the_next_round(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()

    client = StubClient(
        Turn(
            reply="",
            changes_deck=True,
            notes="Keeping the router; the leaf is out.",
            commands=[Select(action="select", request="standup", scope=scope)],
        ),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=[chosen.candidate.id])]),
        Turn(
            reply="",
            changes_deck=True,
            commands=[
                Write(
                    action="write",
                    slides=[paint(Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"]))],
                )
            ],
        ),
        Turn(reply="Done."),
    )

    await talk(client, store, project.id, "standup tomorrow")
    assert "YOUR NOTES" in client.prompts[1]
    assert "Keeping the router; the leaf is out." in client.prompts[1]


async def test_the_cut_sees_each_candidates_source(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()

    client = StubClient(
        Turn(reply="", changes_deck=True, commands=[Select(action="select", request="standup", scope=scope)]),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=[chosen.candidate.id])]),
        Turn(
            reply="",
            changes_deck=True,
            commands=[
                Write(
                    action="write",
                    slides=[paint(Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"]))],
                )
            ],
        ),
        Turn(reply="Done."),
    )

    await talk(client, store, project.id, "standup tomorrow")
    # The keep round must see the file's actual content, not just its id and symbols.
    assert "class Router" in client.prompts[1]


async def test_an_incomplete_deck_can_use_the_final_budgeted_call_to_write(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()
    client = StubClient(
        Turn(
            reply="",
            changes_deck=True,
            commands=[Select(action="select", request="standup", scope=scope)],
        ),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=[chosen.candidate.id])]),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=["src/imaginary.py"])]),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=["src/imaginary.py"])]),
        Turn(
            reply="",
            changes_deck=True,
            commands=[
                Write(
                    action="write",
                    slides=[paint(Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"]))],
                )
            ],
        ),
    )

    assert await talk(client, store, project.id, "standup tomorrow") == "Done - the deck is ready."
    assert len(client.prompts) == agent.MAX_ROUNDS
    assert pipeline.read(store, project.id).slides[0].title == "Router"
    assert "Exactly one command can still run" in client.prompts[-1]


async def test_a_declared_deck_change_without_a_command_stops_honestly(store, project):
    client = StubClient(
        Turn(reply="Here is the slide.", changes_deck=True),
        Turn(reply="I made it.", changes_deck=True),
    )

    assert await talk(client, store, project.id, "create a slide about the architecture") == (
        "I didn't manage to make that change to the deck."
    )
    assert len(client.prompts) == 2


async def test_multiple_commands_are_rejected_before_any_mutation(store, project, index):
    scope = Scope(slide_budget=1)
    commands = [
        Select(action="select", request="standup", scope=scope),
        Keep(action="keep", ids=["src/imaginary.py"]),
    ]
    client = StubClient(
        Turn(reply="", changes_deck=True, commands=commands),
        Turn(reply="I couldn't complete that.", changes_deck=True),
    )

    result = await talk(client, store, project.id, "build it")

    assert result == "I didn't manage to make that change to the deck."
    assert len(client.prompts) == 2
    assert "expected exactly one operation, got 2" in client.prompts[1]
    with pytest.raises(NotFound):
        pipeline.read(store, project.id)


async def test_a_natural_deck_request_uses_the_four_call_build_contract(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()

    client = StubClient(
        Turn(
            reply="",
            changes_deck=True,
            commands=[Select(action="select", request="architecture slide", scope=scope)],
        ),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=[chosen.candidate.id])]),
        Turn(
            reply="",
            changes_deck=True,
            commands=[
                Write(
                    action="write",
                    slides=[paint(Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"]))],
                )
            ],
        ),
        Turn(reply="Created one slide."),
    )

    assert await talk(client, store, project.id, "give me the architecture slide") == "Created one slide."
    assert len(client.prompts) == 4


async def test_a_project_with_nothing_attached_stops_honestly_after_a_failed_change(store):
    empty = store.create("Empty")
    client = StubClient(
        Turn(
            reply="",
            changes_deck=True,
            commands=[Select(action="select", request="s", scope=Scope(slide_budget=1))],
        ),
        Turn(reply="There is nothing to build one from yet."),
    )

    assert await talk(client, store, empty.id, "deck please") == "There is nothing to build one from yet."
    assert len(client.prompts) == 2
    assert "Nothing attached yet" in client.prompts[0]
    assert "select(" in client.prompts[1] and "rejected: this project has nothing attached" in client.prompts[1]


async def test_a_rejected_write_stops_honestly_on_the_next_call(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]

    bad = Slide(candidate_id=chosen.candidate.id, title="T", bullets=["src/ghost.py"])
    client = StubClient(
        Turn(reply="Writing.", changes_deck=True, commands=[Write(action="write", slides=[paint(bad)])]),
        Turn(reply="Fixed it.", changes_deck=True),
    )

    assert await talk(client, store, project.id, "write it") == (
        "I didn't manage to make that change to the deck."
    )
    assert len(client.prompts) == 2
    assert "src/ghost.py" in client.prompts[1]
    assert "write(" in client.prompts[1] and "rejected:" in client.prompts[1]


async def test_a_successful_edit_uses_two_calls_and_drops_the_final_command(store, project, index):
    """A completed edit gets one operational call and one final answer call."""
    deck = pipeline.select(store, project.id, index, "s", Scope(slide_budget=2))
    ids = [entry.candidate.id for entry in deck.selection.chosen]
    pipeline.write(
        store, project.id, index,
        [Slide(candidate_id=cid, title="A slide", bullets=["one"]) for cid in ids],
    )
    swapped = list(reversed(ids))

    reaffirm = Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=swapped)])
    reverts = Turn(reply="Swapped it.", changes_deck=True, commands=[Keep(action="keep", ids=ids)])
    client = StubClient(reaffirm, reverts)

    assert await talk(client, store, project.id, "swap them") == "Swapped it."
    assert len(client.prompts) == 2
    order = [entry.candidate.id for entry in pipeline.read(store, project.id).selection.chosen]
    assert order == swapped


def test_deck_state_shows_an_image_already_written_to_a_slide():
    deck = Deck(
        selection=Selection(request="r", scope=Scope(slide_budget=1)),
        slides=[Slide(candidate_id="pic", free=True, title="Chart", image="repo/chart.png")],
    )
    assert "repo/chart.png" in agent._deck_state(deck)


async def test_a_select_that_matches_nothing_stops_honestly_within_budget(store, project, index):
    empty_select = Select(
        action="select",
        request="work from next century",
        scope=Scope(slide_budget=1, since=datetime(2099, 1, 1, tzinfo=UTC)),
    )
    client = StubClient(
        Turn(reply="", changes_deck=True, commands=[empty_select]),
        Turn(reply="Here is your deck.", changes_deck=True),
    )

    reply = await talk(client, store, project.id, "build a slide about next century's work")
    assert reply == "I couldn't create the deck because that request matched nothing to build slides from."
    assert len(client.prompts) == 1


async def test_a_noop_change_stops_after_one_repeat_within_budget(
    store, project, index
):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    pipeline.write(
        store, project.id, index, [Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"])]
    )
    client = StubClient(
        Turn(reply="Done.", changes_deck=True),
        Turn(reply="Done again.", changes_deck=True),
    )

    reply = await talk(client, store, project.id, "swap the order")
    assert reply == "I didn't manage to make that change to the deck."
    assert len(client.prompts) == 2


async def test_a_needless_reselect_does_not_lose_a_slide_already_written(store, project, index):
    """`select` used to discard every written slide outright, so a model misreading an ordinary
    question as a deck request ("add a slide about X") would wipe a finished deck while reporting
    success - "the slides keep resetting". `select` no longer deletes what it did not invalidate,
    so this needs no keyword-based refusal to hold: the candidate is still chosen either way, and its
    slide rides along."""
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    pipeline.write(
        store,
        project.id,
        index,
        [Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["a"])],
    )
    before = pipeline.read(store, project.id)

    client = StubClient(
        Turn(
            reply="",
            commands=[Select(action="select", request="where is spike", scope=Scope(slide_budget=1))],
        ),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=[chosen.candidate.id])]),
        Turn(reply="Still just the router."),
    )

    reply = await talk(client, store, project.id, "where is the spike and pikachu?")

    after = pipeline.read(store, project.id)
    assert reply == "Still just the router."
    assert after.selection.chosen[0].candidate.id == before.selection.chosen[0].candidate.id
    assert after.slides == before.slides


async def test_the_prompt_shows_what_was_actually_written_on_a_slide(store, project, index):
    scope = Scope(slide_budget=1)
    chosen = pipeline.select(store, project.id, index, "peek", scope).selection.chosen[0]
    pipeline.write(
        store,
        project.id,
        index,
        [Slide(candidate_id=chosen.candidate.id, title="Router", bullets=["dispatches requests"])],
    )

    client = StubClient(Turn(reply="ok"))
    await talk(client, store, project.id, "what does the router slide say?")

    assert "dispatches requests" in client.prompts[0]


async def test_the_prompt_shows_a_free_slides_bullets_too(store, project, index):
    pipeline.select(store, project.id, index, "peek", Scope(slide_budget=1))
    pipeline.write(
        store,
        project.id,
        index,
        [Slide(candidate_id="intro", free=True, title="Welcome", bullets=["say hi to Spike"])],
    )

    client = StubClient(Turn(reply="ok"))
    await talk(client, store, project.id, "what's on the intro slide?")

    assert "say hi to Spike" in client.prompts[0]


async def test_the_prompt_shows_one_true_order_not_a_split_chosen_and_free_view(store, project, index):
    """A trailing free slide's real position used to be invisible - it sat in its own "free:"
    bucket, disconnected from where it actually renders relative to the evidence slides, so "the
    last slide" was ambiguous between the last chosen entry and the last free one."""
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    pipeline.write(
        store,
        project.id,
        index,
        [Slide(candidate_id=e.candidate.id, title="A slide", bullets=["one"]) for e in deck.selection.chosen],
    )
    pipeline.write(store, project.id, index, [Slide(candidate_id="conclusion", free=True, title="The End")])

    client = StubClient(Turn(reply="ok"))
    await talk(client, store, project.id, "what does the deck look like?")

    prompt = client.prompts[0]
    assert "order (top to bottom" in prompt
    assert "\nchosen:\n" not in prompt
    assert "\nfree:\n" not in prompt
    numbered = [line.strip() for line in prompt.splitlines() if re.match(r"^\d+\. ", line.strip())]
    assert len(numbered) == 3
    assert numbered[-1].split(".", 1)[1].strip().startswith("conclusion [free]")


async def test_a_second_turn_reads_back_what_the_first_turn_actually_did(store, project, index, tmp_path):
    """The gap A2 named: no assistant message exists in the request, so nothing carried a command's
    real outcome from one turn to the next - only the model's own possibly-false claim of what it
    did survived. `log` is what closes that: a fresh `converse()` call, simulating the next real
    HTTP turn, can read what actually ran, not just what was said."""
    log = ChatLog(tmp_path / "chat")
    log.append("user", "drop the second slide")
    first = StubClient(Turn(reply="", commands=[Keep(action="keep", ids=["nonexistent"])]), Turn(reply="Done."))
    await agent.converse(first, store, project.id, log.read(), today=TODAY, log=log)

    persisted = log.read()
    assert any(m.role == "command" and "rejected:" in m.content for m in persisted)

    log.append("user", "what happened?")
    second = StubClient(Turn(reply="ok"))
    await agent.converse(second, store, project.id, log.read(), today=TODAY, log=log)

    assert any("rejected:" in outcome for outcome in second.prompts[0].split("\n"))


async def test_the_prompt_echoes_the_standing_scope(store, project, index):
    """Was write-only: the model could set `since`/`keywords`/`slide_budget` but never read them
    back, so "make it 3 slides instead" needed the whole scope re-derived from conversation text."""
    pipeline.select(
        store, project.id, index, "standup",
        Scope(slide_budget=2, keywords=["router"], audience="the team"),
    )

    client = StubClient(Turn(reply="ok"))
    await talk(client, store, project.id, "what's the current scope?")

    assert "scope: 2 slides | keywords router | for the team" in client.prompts[0]


async def test_a_commands_own_outcome_reaches_the_next_round(store, project, index):
    """No assistant turn is ever sent, so the model's only memory of what it tried is this line -
    without it "do not repeat it" asks the model to remember something it was never shown."""
    client = StubClient(
        Turn(reply="", commands=[Keep(action="keep", ids=["nonexistent"])]),
        Turn(reply="ok"),
    )
    await talk(client, store, project.id, "drop the second slide")

    assert "keep(['nonexistent'])" in client.prompts[1]
    assert "rejected:" in client.prompts[1]


async def test_a_final_budget_command_runs_when_the_deck_is_still_incomplete(
    store, project, index
):
    scope = Scope(slide_budget=2)
    selected = pipeline.select(store, project.id, index, "s", scope)
    candidates = [entry.candidate.id for entry in selected.selection.chosen]
    (store.paths(project.id).deck / pipeline.SELECTION_FILE).unlink()

    client = StubClient(
        Turn(
            reply="",
            changes_deck=True,
            commands=[Select(action="select", request="s", scope=scope)],
        ),
        Turn(
            reply="",
            changes_deck=True,
            commands=[Keep(action="keep", ids=candidates[:2])],
        ),
        Turn(reply="I ran out of time.", changes_deck=True),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=["src/imaginary.py"])]),
        Turn(
            reply="",
            changes_deck=True,
            commands=[
                Write(
                    action="write",
                    slides=[
                        paint(Slide(candidate_id=candidate, title="Trailing", bullets=["one"]))
                        for candidate in candidates[:2]
                    ],
                )
            ],
        ),
    )

    result = await talk(client, store, project.id, "build it")

    assert len(client.prompts) == agent.MAX_ROUNDS
    assert "FINAL OPERATIONAL ROUND" in client.prompts[-1]
    assert result == "Done - the deck is ready."
    assert len(pipeline.read(store, project.id).slides) == 2


async def test_history_in_the_prompt_is_capped_at_the_protocol_limit(store, project):
    history = [
        ChatMessage(role="user", content=f"history-marker-{number}", at=TODAY)
        for number in range(agent.MAX_HISTORY_MESSAGES + 8)
    ]
    client = StubClient(Turn(reply="ok"))

    await agent.converse(client, store, project.id, history, today=TODAY)

    assert "history-marker-0" not in client.prompts[0]
    assert f"history-marker-{agent.MAX_HISTORY_MESSAGES}" in client.prompts[0]
    assert f"history-marker-{agent.MAX_HISTORY_MESSAGES + 7}" in client.prompts[0]


async def test_indexed_excerpts_fall_back_to_something_rather_than_nothing(store, monkeypatch):
    made = store.create("Docs")
    described = Index(
        fingerprint="i",
        built_at=TODAY,
        files=[
            FileFacts(
                path="resume-pdf/resume.pdf",
                content_hash="r",
                excerpt="Vincent works on backend systems.",
            )
        ],
    )

    async def indexed(store, project_id):
        return described

    monkeypatch.setattr(agent.pipeline, "indexed", indexed)

    client = StubClient(Turn(reply="ok"))
    # Shares no literal word with the only indexed excerpt.
    await talk(client, store, made.id, "where is spike and pikachu?")

    assert "resume-pdf/resume.pdf" in client.prompts[0]


async def test_a_failed_command_is_not_reported_successfully_without_deck_wording(
    store, project, index
):
    empty_select = Select(
        action="select",
        request="anything",
        scope=Scope(slide_budget=1, since=datetime(2099, 1, 1, tzinfo=UTC)),
    )
    client = StubClient(
        Turn(reply="", changes_deck=True, commands=[empty_select]),
        Turn(reply="Here it is, all set.", changes_deck=True),
    )

    # No "deck"/"slide"/"create" wording: the explicit turn flag still makes the failed change
    # subject to honest verification.
    reply = await talk(client, store, project.id, "can you check on that thing from earlier?")
    assert reply == "I couldn't create the deck because that request matched nothing to build slides from."
    assert len(client.prompts) == 1


async def test_a_successful_command_is_not_mistaken_for_a_rejection(store, project, index):
    """The command result distinguishes a rejected operation from request text containing
    `rejected:`."""
    succeeding_select = Select(
        action="select",
        request="the earlier plan was rejected: broaden the scope",
        scope=Scope(slide_budget=1),
    )
    client = StubClient(
        Turn(reply="", commands=[succeeding_select]),
        Turn(reply="", commands=[]),
        Turn(reply="", commands=[]),
    )

    # No deck/edit wording - only `changed` tracking `select`'s real outcome can catch this.
    reply = await talk(client, store, project.id, "go ahead")
    assert "still needs evidence slides for" in reply
    assert len(client.prompts) == 3


async def test_a_declared_noop_edit_gets_one_retry_before_stopping(store, project, index):
    """An explicit deck-change flag keeps a bare first reply from being reported as a completed
    edit; a real command then gets its own operational round."""
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    pipeline.write(
        store,
        project.id,
        index,
        [
            Slide(candidate_id=entry.candidate.id, title="A slide", bullets=["one"])
            for entry in deck.selection.chosen
        ],
    )
    backwards = [entry.candidate.id for entry in reversed(deck.selection.chosen)]
    client = StubClient(
        Turn(reply="I have swapped the slides.", changes_deck=True),
        Turn(reply="", changes_deck=True, commands=[Keep(action="keep", ids=backwards)]),
        Turn(reply="Done for real this time."),
    )

    reply = await talk(client, store, project.id, "swap slide 6 with slide 1")
    assert reply == "Done for real this time."
    assert len(client.prompts) == 3
    assert agent._NOTHING_RAN in client.prompts[1]
    assert [s.candidate_id for s in pipeline.read(store, project.id).slides] == backwards


async def test_a_swap_that_is_rejected_every_round_is_not_reported_as_done(store, project, index):
    """Rejected operations do not mutate the deck, and the bounded final answer reports that
    honestly instead of trusting the model's claim."""
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    pipeline.write(
        store,
        project.id,
        index,
        [
            Slide(candidate_id=entry.candidate.id, title="A slide", bullets=["one"])
            for entry in deck.selection.chosen
        ],
    )
    before = [entry.candidate.id for entry in pipeline.read(store, project.id).selection.chosen]

    rejected_keep = Turn(reply="", commands=[Keep(action="keep", ids=["nonexistent"])])
    client = StubClient(*[rejected_keep] * (agent.MAX_ROUNDS - 1), Turn(reply="Swapped it."))

    reply = await talk(client, store, project.id, "swap slide 1 and slide 2")
    assert reply == "I didn't manage to make that change to the deck."
    assert len(client.prompts) == agent.MAX_ROUNDS
    after = [entry.candidate.id for entry in pipeline.read(store, project.id).selection.chosen]
    assert after == before


async def test_a_bare_reply_to_a_genuine_question_is_not_retried(store, project, index):
    """The retry is for a stalled edit, not every empty-commands round on a complete deck."""
    deck = pipeline.select(store, project.id, index, "standup", Scope(slide_budget=1))
    pipeline.write(
        store,
        project.id,
        index,
        [Slide(candidate_id=deck.selection.chosen[0].candidate.id, title="A slide", bullets=["one"])],
    )
    client = StubClient(Turn(reply="It covers the auth changes from this week."))

    reply = await talk(client, store, project.id, "what's on the deck so far?")
    assert reply == "It covers the auth changes from this week."
    assert len(client.prompts) == 1


async def test_the_agent_is_never_shown_a_score_or_a_signal(store, project, index):
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=2))
    client = StubClient(Turn(reply="ok"))
    await talk(client, store, project.id, "what is on it?")

    prompt, system = client.prompts[0], client.system
    for banned in ("score", "churn", "centrality", "emphasis", "affinity"):
        assert banned not in prompt.lower()
        assert banned not in system.lower()


async def test_a_slow_pipeline_call_does_not_block_the_event_loop(store, project, index, monkeypatch):
    """`pipeline.read`/`sources` used to run synchronously inside `converse`, so a threadpool
    request holding the project lock could stall every other project's requests too. A tick count
    alone doesn't prove this - it can pass by finishing late, after the block clears, with time to
    spare. This asserts a tick's own timestamp lands strictly inside the blocking call's window,
    which only happens if that window didn't own the event loop."""
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=1))
    window: list[float] = []
    real_read = pipeline.read

    def slow_read(*args, **kwargs):
        window.append(time.perf_counter())
        time.sleep(0.2)
        window.append(time.perf_counter())
        return real_read(*args, **kwargs)

    monkeypatch.setattr(pipeline, "read", slow_read)
    client = StubClient(Turn(reply="ok"))
    tick_times: list[float] = []

    async def ticker() -> None:
        for _ in range(30):
            await asyncio.sleep(0.01)
            tick_times.append(time.perf_counter())

    await asyncio.gather(talk(client, store, project.id, "what is on it?"), ticker())

    assert window, "the blocking read never ran"
    windows = list(zip(window[0::2], window[1::2], strict=True))
    assert any(start < tick < end for start, end in windows for tick in tick_times)
