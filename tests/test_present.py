from datetime import UTC, datetime
from pathlib import Path

import pytest
from pptx import Presentation

from standup.core.models import (
    Candidate,
    Commit,
    FileFacts,
    Index,
    Scope,
    Scored,
    Selection,
    Slide,
    SlidePlan,
    Symbol,
)
from standup.core.present import build, plan, revise
from standup.core.present.validate import problems
from standup.errors import InvalidInput, Upstream

TODAY = datetime(2026, 8, 3, tzinfo=UTC)


class StubClient:
    """Returns each reply in turn, and remembers every prompt it was given."""

    def __init__(self, *replies: SlidePlan) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.system: str | None = None

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.prompts.append(prompt)
        self.system = system
        return self.replies.pop(0)


@pytest.fixture
def index():
    return Index(
        fingerprint="f",
        built_at=TODAY,
        files=[
            FileFacts(
                path="src/auth.py",
                content_hash="a",
                symbols=[Symbol(name="login", kind="Function", line=1)],
            ),
            FileFacts(path="src/billing.py", content_hash="b"),
        ],
        commits=[
            Commit(
                sha="abc",
                authored_at=TODAY,
                author="vince",
                message="signed tokens replace the session store",
                changes={"src/auth.py": 52},
            )
        ],
    )


@pytest.fixture
def selection():
    return Selection(
        request="standup tomorrow, the auth thing",
        scope=Scope(keywords=["auth"], audience="the team", slide_budget=2),
        chosen=[
            Scored(
                candidate=Candidate(
                    id="src/auth.py", title="auth.py", paths=["src/auth.py"], commits=["abc"]
                ),
                signals={"churn": 1.0},
                score=2.4,
            ),
            Scored(
                candidate=Candidate(
                    id="src/billing.py", title="billing.py", paths=["src/billing.py"]
                ),
                signals={"churn": 0.1},
                score=0.3,
            ),
        ],
        cut=[
            Scored(
                candidate=Candidate(id="docs/notes.md", title="notes.md"),
                signals={},
                score=0.01,
            )
        ],
    )


def good_plan() -> SlidePlan:
    return SlidePlan(
        slides=[
            Slide(candidate_id="src/auth.py", title="Auth", bullets=["src/auth.py now signs tokens"]),
            Slide(candidate_id="src/billing.py", title="Billing", bullets=["Untouched this week"]),
        ]
    )


def test_a_clean_plan_has_nothing_wrong_with_it(selection, index):
    assert problems(good_plan(), selection, index) == []


@pytest.mark.parametrize(
    ("slides", "fault"),
    [
        ([], "must be exactly"),
        ([Slide(candidate_id="src/auth.py", title="Only one")], "must be exactly"),
        (
            [
                Slide(candidate_id="src/billing.py", title="Billing"),
                Slide(candidate_id="src/auth.py", title="Auth"),
            ],
            "in that order",
        ),
        (
            [
                Slide(candidate_id="src/auth.py", title="Auth"),
                Slide(candidate_id="src/auth.py", title="Auth again"),
            ],
            "must be exactly",
        ),
    ],
)
def test_the_plan_cannot_add_drop_reorder_or_repeat_a_slide(selection, index, slides, fault):
    assert any(fault in problem for problem in problems(SlidePlan(slides=slides), selection, index))


def test_a_file_that_does_not_exist_is_refused(selection, index):
    drafted = good_plan()
    drafted.slides[0].bullets = ["Rewrote src/auth/oauth.py to issue tokens"]
    assert any("no file 'src/auth/oauth.py'" in p for p in problems(drafted, selection, index))


def test_a_symbol_that_does_not_exist_is_refused(selection, index):
    drafted = good_plan()
    drafted.slides[0].bullets = ["refresh_token() was added"]
    assert any("no 'refresh_token'" in p for p in problems(drafted, selection, index))


def test_prose_that_merely_looks_like_a_path_is_left_alone(selection, index):
    drafted = good_plan()
    drafted.slides[0].bullets = ["Tokens are signed and/or encrypted, e.g. on login"]
    assert problems(drafted, selection, index) == []


async def test_the_model_sees_the_evidence_but_not_the_scores_or_the_cut(selection, index):
    client = StubClient(good_plan())
    await plan(client, selection, index)
    prompt = client.prompts[0]

    assert "signed tokens replace the session store" in prompt
    assert "the team" in prompt
    assert "docs/notes.md" not in prompt
    for banned in ("2.4", "0.3", "churn"):
        assert banned not in prompt


async def test_the_audience_reaches_the_prompt_only_when_the_scope_found_one(selection, index):
    stated = StubClient(good_plan())
    await plan(stated, selection, index)
    assert "Audience: the team" in stated.prompts[0]

    selection.scope.audience = None
    quiet = StubClient(good_plan())
    await plan(quiet, selection, index)
    assert "Audience" not in quiet.prompts[0]


async def test_a_deleted_file_can_still_be_written_about(selection, index):
    index.files = [facts for facts in index.files if facts.path != "src/auth.py"]
    drafted = good_plan()
    drafted.slides[0].bullets = ["src/auth.py was removed"]
    assert problems(drafted, selection, index) == []


async def test_a_bad_plan_is_sent_back_once_with_what_was_wrong(selection, index):
    broken = SlidePlan(slides=[Slide(candidate_id="src/auth.py", title="Only one")])
    client = StubClient(broken, good_plan())

    assert await plan(client, selection, index) == good_plan()
    assert len(client.prompts) == 2
    assert "rejected" in client.prompts[1]


async def test_a_plan_that_stays_wrong_fails_closed(selection, index):
    broken = SlidePlan(slides=[Slide(candidate_id="src/auth.py", title="Only one")])
    client = StubClient(broken, broken)
    with pytest.raises(Upstream, match="could not be grounded"):
        await plan(client, selection, index)


def test_removing_and_reordering_a_selection_costs_no_model_call(selection):
    selection.chosen.reverse()
    revised = revise(good_plan(), selection)
    assert [s.candidate_id for s in revised.slides] == ["src/billing.py", "src/auth.py"]

    selection.chosen.pop()
    assert [s.candidate_id for s in revise(good_plan(), selection).slides] == ["src/billing.py"]


def test_restoring_a_cut_item_needs_a_slide_written_for_it(selection):
    selection.chosen.append(selection.cut[0])
    with pytest.raises(InvalidInput, match="docs/notes.md"):
        revise(good_plan(), selection)


def test_the_deck_opens_with_the_slides_it_was_given(tmp_path):
    written = build(good_plan(), tmp_path / "decks" / "standup.pptx")
    assert written.is_file()

    reopened = Presentation(str(written))
    assert [s.shapes.title.text for s in reopened.slides] == ["Auth", "Billing"]
    assert "src/auth.py now signs tokens" in reopened.slides[0].shapes[1].text_frame.text


def test_a_slide_with_several_bullets_keeps_them_all(tmp_path):
    many = SlidePlan(
        slides=[Slide(candidate_id="src/auth.py", title="Auth", bullets=["one", "two", "three"])]
    )
    written = build(many, Path(tmp_path) / "many.pptx")
    body = Presentation(str(written)).slides[0].shapes[1].text_frame
    assert [p.text for p in body.paragraphs] == ["one", "two", "three"]
