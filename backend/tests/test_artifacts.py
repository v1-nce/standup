from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from models import (
    Brief,
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


@pytest.fixture
def selection():
    candidate = Candidate(id="auth", title="Auth refactor", paths=["src/auth.py"], commits=["abc"])
    return Selection(
        request="standup tomorrow, the auth thing, three slides",
        scope=Scope(since=datetime(2026, 8, 1, tzinfo=UTC), keywords=["auth"], slide_budget=3),
        chosen=[
            Scored(
                candidate=candidate,
                brief=Brief(
                    candidate_id="auth",
                    what_changed="Sessions moved to signed tokens",
                    why_it_matters="Removes the shared session store",
                    evidence=["src/auth.py", "abc"],
                ),
                signals={"churn": 0.8, "rank": 0.4},
                score=0.62,
            )
        ],
        cut=[Scored(candidate=Candidate(id="readme", title="README tidy"), score=0.03)],
    )


def test_index_round_trips():
    index = Index(
        fingerprint="cafe1234",
        built_at=datetime(2026, 8, 3, tzinfo=UTC),
        files=[
            FileFacts(
                path="src/auth.py",
                content_hash="deadbeef",
                symbols=[Symbol(name="login", kind="function", line=12)],
                imports=["src/db.py"],
            )
        ],
        commits=[
            Commit(
                sha="abc",
                authored_at=datetime(2026, 8, 2, tzinfo=UTC),
                author="vince",
                message="signed tokens",
                changes={"src/auth.py": 52},
            )
        ],
        rank={"src/auth.py": 0.91},
        emphasis={"src/auth.py": 0.5},
    )
    assert Index.model_validate_json(index.model_dump_json()) == index


def test_selection_round_trips_with_its_reasons(selection):
    restored = Selection.model_validate_json(selection.model_dump_json())
    assert restored == selection
    assert restored.chosen[0].signals["churn"] == 0.8
    assert restored.cut[0].candidate.id == "readme"


def test_slide_plan_names_the_candidate_it_came_from(selection):
    plan = SlidePlan(slides=[Slide(candidate_id="auth", title="Auth refactor", bullets=["one"])])
    assert {s.candidate_id for s in plan.slides} <= {s.candidate.id for s in selection.chosen}


def test_a_deck_of_no_slides_is_not_a_scope():
    with pytest.raises(ValidationError):
        Scope(slide_budget=0)
