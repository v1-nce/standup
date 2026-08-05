from datetime import UTC, datetime

import pytest

from standup.core.gather import candidates, validated
from standup.core.models import Commit, FileFacts, Index, Scope
from standup.errors import InvalidInput

MONDAY = datetime(2026, 7, 27, tzinfo=UTC)
THURSDAY = datetime(2026, 7, 30, tzinfo=UTC)
TODAY = datetime(2026, 8, 3, tzinfo=UTC)


def make_index(*, commits=(), complete=True) -> Index:
    return Index(
        fingerprint="abc",
        built_at=TODAY,
        history_complete=complete,
        files=[
            FileFacts(path="src/auth.py", content_hash="a"),
            FileFacts(path="src/billing.py", content_hash="b"),
            FileFacts(path="README.md", content_hash="c"),
        ],
        commits=list(commits),
    )


def commit(sha: str, at: datetime, *paths: str) -> Commit:
    return Commit(
        sha=sha, authored_at=at, author="vince", message=sha, changes=dict.fromkeys(paths, 10)
    )


@pytest.fixture
def index():
    return make_index(
        commits=[
            commit("recent", THURSDAY, "src/auth.py"),
            commit("older", MONDAY, "src/billing.py"),
        ]
    )


def test_a_window_keeps_only_what_changed_inside_it(index):
    chosen = candidates(index, Scope(since=THURSDAY, slide_budget=3))
    assert [c.id for c in chosen] == ["src/auth.py"]
    assert chosen[0].commits == ["recent"]


def test_no_window_puts_the_whole_index_in_play(index):
    chosen = candidates(index, Scope(slide_budget=3))
    assert [c.id for c in chosen] == ["README.md", "src/auth.py", "src/billing.py"]


def test_candidates_carry_only_the_commits_inside_the_window(index):
    index.commits.append(commit("ancient", datetime(2026, 1, 1, tzinfo=UTC), "src/auth.py"))
    chosen = candidates(index, Scope(since=MONDAY, slide_budget=3))
    assert {c.id: c.commits for c in chosen} == {
        "src/auth.py": ["recent"],
        "src/billing.py": ["older"],
    }


def test_candidates_come_out_in_a_stable_order(index):
    twice = [candidates(index, Scope(slide_budget=3)) for _ in range(2)]
    assert twice[0] == twice[1]


def test_a_scope_drops_paths_the_index_has_never_heard_of(index):
    settled = validated(
        Scope(paths=["auth", "src/imaginary"], keywords=["auth"], slide_budget=3), index
    )
    assert settled.paths == ["auth"]
    assert settled.keywords == ["auth"]


def test_a_window_that_ends_before_it_starts_is_refused(index):
    with pytest.raises(InvalidInput):
        validated(Scope(since=THURSDAY, until=MONDAY, slide_budget=3), index)


def test_a_file_deleted_in_the_window_is_still_work_done(index):
    index.commits.append(commit("removal", THURSDAY, "src/legacy.py"))
    chosen = candidates(index, Scope(since=THURSDAY, slide_budget=3))
    assert [c.id for c in chosen] == ["src/auth.py", "src/legacy.py"]
    assert chosen[1].commits == ["removal"]


def test_a_window_reaching_past_a_capped_history_is_refused(index):
    capped = make_index(commits=index.commits, complete=False)
    with pytest.raises(InvalidInput, match="most recent"):
        validated(Scope(since=datetime(2020, 1, 1, tzinfo=UTC), slide_budget=3), capped)


def test_a_window_inside_a_capped_history_is_still_answered(index):
    capped = make_index(commits=index.commits, complete=False)
    assert validated(Scope(since=THURSDAY, slide_budget=3), capped)


def test_a_window_without_history_is_refused_rather_than_guessed():
    with pytest.raises(InvalidInput, match="no git history"):
        validated(Scope(since=MONDAY, slide_budget=3), make_index())


def test_the_settled_scope_is_what_narrows_the_candidates(index):
    settled = validated(Scope(since=THURSDAY, keywords=["auth"], slide_budget=2), index)
    assert settled.keywords == ["auth"]
    assert [c.id for c in candidates(index, settled)] == ["src/auth.py"]
