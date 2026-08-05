from datetime import UTC, datetime

import pytest

from standup.core.models import Candidate, Commit, FileFacts, Index, Scope
from standup.core.selection import choose
from standup.core.selection.diversity import _overlap, ordered
from standup.core.selection.score import WEIGHTS, relevance
from standup.core.selection.signals import SIGNALS, measure

TODAY = datetime(2026, 8, 3, tzinfo=UTC)


def commit(sha: str, day: int, *paths: str, size: int = 10) -> Commit:
    return Commit(
        sha=sha,
        authored_at=datetime(2026, 8, day, tzinfo=UTC),
        author="vince",
        message=f"{sha} message",
        changes=dict.fromkeys(paths, size),
    )


@pytest.fixture
def index():
    return Index(
        fingerprint="f",
        built_at=TODAY,
        files=[
            FileFacts(path=path, content_hash="h")
            for path in ("src/auth/login.py", "src/auth/session.py", "src/billing/invoice.py")
        ],
        commits=[
            commit("big", 2, "src/auth/login.py", size=400),
            commit("small", 1, "src/auth/session.py", size=5),
            commit("mid", 1, "src/billing/invoice.py", size=50),
        ],
        rank={"src/auth/login.py": 0.5, "src/billing/invoice.py": 0.2},
        emphasis={"src/billing/invoice.py": 1.0},
    )


@pytest.fixture
def candidates():
    return [
        Candidate(id="src/auth/login.py", title="login.py", paths=["src/auth/login.py"], commits=["big"]),
        Candidate(id="src/auth/session.py", title="session.py", paths=["src/auth/session.py"], commits=["small"]),
        Candidate(id="src/billing/invoice.py", title="invoice.py", paths=["src/billing/invoice.py"], commits=["mid"]),
    ]


def test_every_signal_is_reported_for_every_candidate(index, candidates):
    signals = measure(candidates, index, Scope(slide_budget=2))
    assert set(signals) == {c.id for c in candidates}
    for values in signals.values():
        assert set(values) == set(SIGNALS)
        assert all(0.0 <= value <= 1.0 for value in values.values())


def test_a_candidate_with_no_evidence_for_a_signal_scores_zero_not_missing(index, candidates):
    signals = measure(candidates, index, Scope(slide_budget=2))
    assert signals["src/auth/session.py"]["centrality"] == 0.0
    assert signals["src/auth/login.py"]["churn"] == 1.0


def test_the_request_weights_a_candidate_up_without_excluding_the_others(index, candidates):
    quiet = measure(candidates, index, Scope(slide_budget=2))
    steered = measure(candidates, index, Scope(keywords=["billing"], slide_budget=2))

    assert steered["src/billing/invoice.py"]["affinity"] > quiet["src/billing/invoice.py"]["affinity"]
    assert relevance(steered["src/auth/login.py"]) > 0


def test_every_registered_signal_carries_a_weight():
    assert set(WEIGHTS) == set(SIGNALS)


def test_overlap_sees_a_shared_directory_and_a_shared_commit():
    here = Candidate(id="src/auth/login.py", title="a", commits=["x"])
    sibling = Candidate(id="src/auth/session.py", title="b", commits=["y"])
    stranger = Candidate(id="docs/guide.md", title="c", commits=["z"])
    co_committed = Candidate(id="docs/other.md", title="d", commits=["x"])

    assert _overlap(here, sibling) == 1.0
    assert _overlap(here, stranger) == 0.0
    assert _overlap(here, co_committed) == 1.0


@pytest.fixture
def rivals():
    """b repeats a's subsystem; c opens a new one. Only their relevance gap differs per case."""
    return [
        Candidate(id="src/auth/a.py", title="a", commits=[]),
        Candidate(id="src/auth/b.py", title="b", commits=[]),
        Candidate(id="src/billing/c.py", title="c", commits=[]),
    ]


def test_a_near_tie_goes_to_the_untouched_subsystem(rivals):
    scores = {"src/auth/a.py": 1.0, "src/auth/b.py": 0.72, "src/billing/c.py": 0.70}
    assert [c.id for c in ordered(rivals, scores, 2)] == ["src/auth/a.py", "src/billing/c.py"]


def test_diversity_does_not_overturn_a_wide_relevance_gap(rivals):
    scores = {"src/auth/a.py": 1.0, "src/auth/b.py": 0.9, "src/billing/c.py": 0.5}
    assert [c.id for c in ordered(rivals, scores, 2)] == ["src/auth/a.py", "src/auth/b.py"]


def test_selection_carries_what_was_cut_and_why(index, candidates):
    selection = choose(index, Scope(slide_budget=2), candidates, request="standup tomorrow")

    assert len(selection.chosen) == 2
    assert len(selection.cut) == 1
    assert selection.request == "standup tomorrow"
    for entry in [*selection.chosen, *selection.cut]:
        assert set(entry.signals) == set(SIGNALS)
        assert entry.score == pytest.approx(relevance(entry.signals))


def test_the_same_index_and_request_choose_identically_twice(index, candidates):
    scope = Scope(keywords=["auth"], slide_budget=2)
    first = choose(index, scope, candidates, request="the auth thing")
    second = choose(index, scope, candidates, request="the auth thing")
    assert first.model_dump_json() == second.model_dump_json()


def test_a_budget_larger_than_the_evidence_cuts_nothing(index, candidates):
    selection = choose(index, Scope(slide_budget=10), candidates, request="everything")
    assert len(selection.chosen) == 3
    assert selection.cut == []
