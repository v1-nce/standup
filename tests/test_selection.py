from datetime import UTC, datetime

import pytest

from standup.core.models import (
    Candidate,
    Commit,
    FileFacts,
    Index,
    Memory,
    MemoryEntry,
    Scope,
)
from standup.core.selection import choose
from standup.core.selection.diversity import _overlap, ordered
from standup.core.selection.score import WEIGHTS, relevance
from standup.core.selection.signals import SIGNALS, _churn, measure

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


def test_churn_compresses_a_mega_commit_instead_of_letting_it_zero_out_a_real_change():
    """Linear min-max against a lockfile-sized diff used to pin every genuine change near 0 -
    log1p keeps the ordering (a bigger real change still outranks a tiny one) while stopping one
    outlier from swallowing the whole scale."""
    tiny = Commit(sha="t", authored_at=TODAY, author="v", message="m", changes={"typo.py": 1})
    normal = Commit(sha="n", authored_at=TODAY, author="v", message="m", changes={"app.py": 200})
    mega = Commit(sha="m", authored_at=TODAY, author="v", message="m", changes={"lockfile": 200_000})
    index = Index(fingerprint="f", built_at=TODAY, commits=[tiny, normal, mega])
    candidates = [
        Candidate(id="typo.py", paths=["typo.py"], commits=["t"]),
        Candidate(id="app.py", paths=["app.py"], commits=["n"]),
        Candidate(id="lockfile", paths=["lockfile"], commits=["m"]),
    ]

    raw = _churn(candidates, index, Scope(slide_budget=3))
    assert raw["typo.py"] < raw["app.py"] < raw["lockfile"]  # ordering preserved

    scaled = measure(candidates, index, Scope(slide_budget=3))
    # Linear would put app.py at ~(200-1)/200_000 =~ 0.001; log1p keeps it a real fraction of scale.
    assert scaled["app.py"]["churn"] > 0.3


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


def test_affinity_does_not_match_a_keyword_inside_an_unrelated_word():
    """"auth" used to match inside "author" - a substring count, not a mention."""
    candidate = Candidate(id="notes", paths=["notes/one.md"])
    unrelated = Index(
        fingerprint="f",
        built_at=TODAY,
        files=[FileFacts(path="notes/one.md", content_hash="h", excerpt="Written by the author.")],
    )
    hits = SIGNALS["affinity"]([candidate], unrelated, Scope(keywords=["auth"], slide_budget=1))
    assert hits.get("notes", 0.0) == 0.0


def test_affinity_matches_a_keyword_as_a_compound_filename_suffix():
    """selectreactor.py is about the reactor even though the term is glued to a prefix - a
    filename is one compound word. The right boundary still blocks a prefix match (auth in author)."""
    candidate = Candidate(id="twisted/internet/selectreactor.py", paths=["twisted/internet/selectreactor.py"])
    related = Index(
        fingerprint="f",
        built_at=TODAY,
        files=[FileFacts(path="twisted/internet/selectreactor.py", content_hash="h")],
    )
    hits = SIGNALS["affinity"]([candidate], related, Scope(keywords=["reactor"], slide_budget=1))
    assert hits.get(candidate.id, 0.0) > 0


def test_affinity_still_does_not_match_a_prefix_in_the_filename():
    """auth must not match author.py - the right boundary is what prevents that, and it stays."""
    candidate = Candidate(id="author.py", paths=["author.py"])
    related = Index(
        fingerprint="f",
        built_at=TODAY,
        files=[FileFacts(path="author.py", content_hash="h")],
    )
    hits = SIGNALS["affinity"]([candidate], related, Scope(keywords=["auth"], slide_budget=1))
    assert hits.get(candidate.id, 0.0) == 0.0


def test_affinity_still_matches_the_keyword_as_its_own_word():
    candidate = Candidate(id="notes", paths=["notes/one.md"])
    related = Index(
        fingerprint="f",
        built_at=TODAY,
        files=[FileFacts(path="notes/one.md", content_hash="h", excerpt="Reworked auth end to end.")],
    )
    hits = SIGNALS["affinity"]([candidate], related, Scope(keywords=["auth"], slide_budget=1))
    assert hits.get("notes", 0.0) > 0


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


def test_overlap_sees_a_shared_directory_but_not_a_shared_commit():
    """A shared commit used to count as overlap too, on the theory that shared authorship means
    shared coverage - backwards: a commit spanning several files is one change, and MMR splitting
    it across slides for "diversity" is a worse deck, not a more diverse one."""
    here = Candidate(id="app/src/auth/login.py", title="a", commits=["x"])
    sibling = Candidate(id="app/src/auth/session.py", title="b", commits=["y"])
    stranger = Candidate(id="app/docs/guide.md", title="c", commits=["z"])
    co_committed = Candidate(id="app/docs/other.md", title="d", commits=["x"])

    assert _overlap(here, sibling) == 1.0
    assert _overlap(here, stranger) == 0.0
    assert _overlap(here, co_committed) == 0.0


def test_overlap_never_conflates_two_different_resources():
    """Two root-level files from different resources used to both reduce to () and score 1.0."""
    doc_a = Candidate(id="docA/notes.md", title="a")
    doc_b = Candidate(id="docB/readme.md", title="b")
    assert _overlap(doc_a, doc_b) == 0.0


def test_overlap_treats_two_unrelated_root_files_as_no_information_not_maximal():
    """Both sitting at their resource's root used to hit a `0/0 -> 1.0` branch, so README.md and
    Dockerfile - sharing nothing but the absence of a subdirectory - scored as maximally redundant."""
    readme = Candidate(id="app/README.md", title="a")
    dockerfile = Candidate(id="app/Dockerfile", title="b")
    assert _overlap(readme, dockerfile) == 0.0


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


def test_only_a_razor_thin_tie_goes_to_the_untouched_subsystem(rivals):
    """LAMBDA=0.95 (see diversity.py) needs a normalized gap under ~5% to flip a pick - measured
    2026-08-14 against 3 real quality-benchmark cases, where a looser near-tie threshold (0.7) cost
    average recall almost exactly in half. This is what diversity can still do at that weight."""
    scores = {"app/src/auth/a.py": 1.0, "app/src/auth/b.py": 0.50, "app/src/billing/c.py": 0.49}
    assert [c.id for c in ordered(rivals, scores, 2)] == ["app/src/auth/a.py", "app/src/billing/c.py"]


def test_a_near_tie_that_used_to_flip_no_longer_does(rivals):
    """The exact case that motivated LAMBDA=0.7 originally - proof the retuned weight is a real,
    deliberate change of behaviour, not just a smaller number. Real architectures often concentrate
    in one directory; pushing away from it here was the wrong call, per the same measurement."""
    scores = {"app/src/auth/a.py": 1.0, "app/src/auth/b.py": 0.72, "app/src/billing/c.py": 0.70}
    assert [c.id for c in ordered(rivals, scores, 2)] == ["app/src/auth/a.py", "app/src/auth/b.py"]


def test_diversity_does_not_overturn_a_wide_relevance_gap(rivals):
    scores = {"app/src/auth/a.py": 1.0, "app/src/auth/b.py": 0.9, "app/src/billing/c.py": 0.5}
    assert [c.id for c in ordered(rivals, scores, 2)] == ["app/src/auth/a.py", "app/src/auth/b.py"]


def test_ordered_is_invariant_to_relevances_raw_scale():
    """The actual thing S1 fixed: `ordered()` must normalise before weighing, so the same relative
    picture - not the absolute numbers - drives the outcome. `relevance()` sums WEIGHTS to 0-5.1, not
    0-1; scored directly against raw values in that range, the old code let an outlier candidate
    compress every real gap toward the diversity ceiling's noise floor. Proven here by scoring the
    identical relative shape once at 0-1 and once at a realistic 0-5 range and requiring the same
    pick both times."""
    candidates = [
        Candidate(id="app/src/auth/a.py", title="a"),
        Candidate(id="app/src/auth/b.py", title="b"),  # redundant with a: same directory
        Candidate(id="app/billing/c.py", title="c"),  # a different subsystem entirely
        Candidate(id="app/other/d.py", title="d"),  # far below the rest, only stretches the range
    ]
    small = {"app/src/auth/a.py": 1.0, "app/src/auth/b.py": 0.6, "app/billing/c.py": 0.4, "app/other/d.py": 0.0}
    scaled_up = {path: value * 5 for path, value in small.items()}
    assert (
        [c.id for c in ordered(candidates, small, 2)]
        == [c.id for c in ordered(candidates, scaled_up, 2)]
    )


def test_selection_carries_what_was_cut_and_why(index, candidates):
    selection = choose(index, Scope(slide_budget=2), candidates, request="standup tomorrow")

    assert len(selection.chosen) == 2
    assert len(selection.cut) == 1
    assert selection.request == "standup tomorrow"
    for entry in [*selection.chosen, *selection.cut]:
        assert set(entry.signals) == set(SIGNALS)
        assert entry.score == pytest.approx(relevance(entry.signals))

    # "and why" used to be untested - a cut item narrates the same score/signals a chosen one
    # carries silently; a chosen item needs no such explanation.
    assert all(entry.reason is None for entry in selection.chosen)
    assert all(entry.reason and "below the cutoff" in entry.reason for entry in selection.cut)


def test_the_same_index_and_request_choose_identically_twice(index, candidates):
    scope = Scope(keywords=["auth"], slide_budget=2)
    first = choose(index, scope, candidates, request="the auth thing")
    second = choose(index, scope, candidates, request="the auth thing")
    assert first.model_dump_json() == second.model_dump_json()


def test_a_budget_larger_than_the_evidence_cuts_nothing(index, candidates):
    selection = choose(index, Scope(slide_budget=10), candidates, request="everything")
    assert len(selection.chosen) == 3
    assert selection.cut == []


def test_memory_prefers_a_previously_kept_candidate_over_an_unseen_one(index, candidates):
    memory = Memory(
        entries=[MemoryEntry(at=TODAY, request="prior", kept=["app/src/auth/session.py"])]
    )
    scored = measure(candidates, index, Scope(slide_budget=2), memory)
    assert scored["app/src/auth/session.py"]["memory"] > scored["app/src/auth/login.py"]["memory"]


def test_memory_puts_a_previously_cut_candidate_below_an_unseen_one(index, candidates):
    memory = Memory(
        entries=[MemoryEntry(at=TODAY, request="prior", cut=["app/src/auth/login.py"])]
    )
    scored = measure(candidates, index, Scope(slide_budget=2), memory)
    assert scored["app/src/auth/login.py"]["memory"] < scored["app/src/auth/session.py"]["memory"]


def test_memory_uses_the_latest_disposition_not_a_running_tally(index, candidates):
    memory = Memory(
        entries=[
            MemoryEntry(at=TODAY, request="first", kept=["app/src/auth/login.py"]),
            MemoryEntry(at=TODAY, request="second", cut=["app/src/auth/login.py"]),
        ]
    )
    scored = measure(candidates, index, Scope(slide_budget=2), memory)
    assert scored["app/src/auth/login.py"]["memory"] == 0.0
    assert scored["app/src/auth/session.py"]["memory"] == 1.0
