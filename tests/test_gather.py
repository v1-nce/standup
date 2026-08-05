from datetime import UTC, datetime

import pytest

from standup.core.gather import candidates, scope
from standup.core.models import Commit, FileFacts, Index, Scope
from standup.errors import InvalidInput

MONDAY = datetime(2026, 7, 27, tzinfo=UTC)
THURSDAY = datetime(2026, 7, 30, tzinfo=UTC)
TODAY = datetime(2026, 8, 3, tzinfo=UTC)


class StubClient:
    """Stands in for the model. Records what it was asked, returns what the test decides."""

    def __init__(self, reply: Scope) -> None:
        self.reply = reply
        self.prompt = None
        self.system = None

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.prompt, self.system = prompt, system
        return self.reply


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


async def test_scope_drops_paths_the_index_has_never_heard_of(index):
    client = StubClient(Scope(paths=["auth", "src/imaginary"], keywords=["auth"], slide_budget=3))
    settled = await scope(client, "the auth thing", index=index, today=TODAY, slide_budget=3)
    assert settled.paths == ["auth"]
    assert settled.keywords == ["auth"]


async def test_scope_refuses_a_window_that_ends_before_it_starts(index):
    client = StubClient(Scope(since=THURSDAY, until=MONDAY, slide_budget=3))
    with pytest.raises(InvalidInput):
        await scope(client, "last week", index=index, today=TODAY, slide_budget=3)


def test_a_file_deleted_in_the_window_is_still_work_done(index):
    index.commits.append(commit("removal", THURSDAY, "src/legacy.py"))
    chosen = candidates(index, Scope(since=THURSDAY, slide_budget=3))
    assert [c.id for c in chosen] == ["src/auth.py", "src/legacy.py"]
    assert chosen[1].commits == ["removal"]


async def test_a_window_reaching_past_a_capped_history_is_refused(index):
    capped = make_index(commits=index.commits, complete=False)
    client = StubClient(Scope(since=datetime(2020, 1, 1, tzinfo=UTC), slide_budget=3))
    with pytest.raises(InvalidInput, match="most recent"):
        await scope(client, "since 2020", index=capped, today=TODAY, slide_budget=3)


async def test_a_window_inside_a_capped_history_is_still_answered(index):
    capped = make_index(commits=index.commits, complete=False)
    client = StubClient(Scope(since=THURSDAY, slide_budget=3))
    assert await scope(client, "since Thursday", index=capped, today=TODAY, slide_budget=3)


async def test_a_window_without_history_is_refused_rather_than_guessed():
    client = StubClient(Scope(since=MONDAY, slide_budget=3))
    with pytest.raises(InvalidInput, match="no git history"):
        await scope(client, "since Monday", index=make_index(), today=TODAY, slide_budget=3)


async def test_the_model_is_told_the_date_but_never_the_candidates(index):
    client = StubClient(Scope(slide_budget=3))
    await scope(client, "standup tomorrow", index=index, today=TODAY, slide_budget=3)
    assert "2026-08-03" in client.prompt
    assert "standup tomorrow" in client.prompt
    for path in ("src/auth.py", "src/billing.py", "README.md"):
        assert path not in client.prompt
        assert path not in client.system


async def test_the_settled_scope_is_what_narrows_the_candidates(index):
    client = StubClient(Scope(since=THURSDAY, keywords=["auth"], slide_budget=2))
    settled = await scope(client, "the auth thing", index=index, today=TODAY, slide_budget=2)
    assert settled.keywords == ["auth"]
    assert [c.id for c in candidates(index, settled)] == ["src/auth.py"]
