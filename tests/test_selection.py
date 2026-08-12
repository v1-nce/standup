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
            for path in ("app/src/auth/login.py", "app/src/auth/session.py", "app/src/billing/invoice.py")
        ],
        commits=[
            commit("big", 2, "app/src/auth/login.py", size=400),
            commit("small", 1, "app/src/auth/session.py", size=5),
            commit("mid", 1, "app/src/billing/invoice.py", size=50),
        ],
        rank={"app/src/auth/login.py": 0.5, "app/src/billing/invoice.py": 0.2},
        emphasis={"app/src/billing/invoice.py": 1.0},
    )


@pytest.fixture
def candidates():
    return [
        Candidate(id="app/src/auth/login.py", title="login.py", paths=["app/src/auth/login.py"], commits=["big"]),
        Candidate(id="app/src/auth/session.py", title="session.py", paths=["app/src/auth/session.py"], commits=["small"]),
        Candidate(id="app/src/billing/invoice.py", title="invoice.py", paths=["app/src/billing/invoice.py"], commits=["mid"]),
    ]


def test_every_signal_is_reported_for_every_candidate(index, candidates):
    signals = measure(candidates, index, Scope(slide_budget=2))
    assert set(signals) == {c.id for c in candidates}
    for values in signals.values():
        assert set(values) == set(SIGNALS)
        assert all(0.0 <= value <= 1.0 for value in values.values())


def test_a_candidate_with_no_evidence_for_a_signal_scores_zero_not_missing(index, candidates):
    signals = measure(candidates, index, Scope(slide_budget=2))
    assert signals["app/src/auth/session.py"]["centrality"] == 0.0
    assert signals["app/src/auth/login.py"]["churn"] == 1.0


def test_the_request_weights_a_candidate_up_without_excluding_the_others(index, candidates):
    quiet = measure(candidates, index, Scope(slide_budget=2))
    steered = measure(candidates, index, Scope(keywords=["billing"], slide_budget=2))

    assert steered["app/src/billing/invoice.py"]["affinity"] > quiet["app/src/billing/invoice.py"]["affinity"]
    assert relevance(steered["app/src/auth/login.py"]) > 0


def test_every_registered_signal_carries_a_weight():
    assert set(WEIGHTS) == set(SIGNALS)


def test_affinity_credits_whichever_of_a_candidate_s_paths_carries_the_excerpt():
    """_churn treats candidate.paths as the file list; _affinity used to only check candidate.id."""
    candidate = Candidate(id="notes", title="notes", paths=["notes/one.md", "notes/two.md"])
    two_docs = Index(
        fingerprint="f",
        built_at=TODAY,
        files=[
            FileFacts(path="notes/one.md", content_hash="h1"),
            FileFacts(path="notes/two.md", content_hash="h2", excerpt="the billing rollout"),
        ],
    )
    hits = SIGNALS["affinity"]([candidate], two_docs, Scope(keywords=["billing"], slide_budget=1))
    assert hits.get("notes", 0.0) > 0


def test_overlap_sees_a_shared_directory_and_a_shared_commit():
    here = Candidate(id="app/src/auth/login.py", title="a", commits=["x"])
    sibling = Candidate(id="app/src/auth/session.py", title="b", commits=["y"])
    stranger = Candidate(id="app/docs/guide.md", title="c", commits=["z"])
    co_committed = Candidate(id="app/docs/other.md", title="d", commits=["x"])

    assert _overlap(here, sibling) == 1.0
    assert _overlap(here, stranger) == 0.0
    assert _overlap(here, co_committed) == 1.0


def test_overlap_never_conflates_two_different_resources():
    """Two root-level files from different resources used to both reduce to () and score 1.0."""
    doc_a = Candidate(id="docA/notes.md", title="a")
    doc_b = Candidate(id="docB/readme.md", title="b")
    assert _overlap(doc_a, doc_b) == 0.0


def test_overlap_needs_a_shared_prefix_not_just_a_same_depth_folder_name():
    """These diverge at the very first directory; a positional zip used to still credit 'models/'."""
    backend = Candidate(id="app/backend/models/user.py", title="a")
    frontend = Candidate(id="app/frontend/models/product.py", title="b")
    assert _overlap(backend, frontend) == 0.0


@pytest.fixture
def rivals():
    """b repeats a's subsystem; c opens a new one. Only their relevance gap differs per case."""
    return [
        Candidate(id="app/src/auth/a.py", title="a", commits=[]),
        Candidate(id="app/src/auth/b.py", title="b", commits=[]),
        Candidate(id="app/src/billing/c.py", title="c", commits=[]),
    ]


def test_a_near_tie_goes_to_the_untouched_subsystem(rivals):
    scores = {"app/src/auth/a.py": 1.0, "app/src/auth/b.py": 0.72, "app/src/billing/c.py": 0.70}
    assert [c.id for c in ordered(rivals, scores, 2)] == ["app/src/auth/a.py", "app/src/billing/c.py"]


def test_diversity_does_not_overturn_a_wide_relevance_gap(rivals):
    scores = {"app/src/auth/a.py": 1.0, "app/src/auth/b.py": 0.9, "app/src/billing/c.py": 0.5}
    assert [c.id for c in ordered(rivals, scores, 2)] == ["app/src/auth/a.py", "app/src/auth/b.py"]


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
