"""What the request puts in play: one model call for scope, then the index does the rest."""

from datetime import UTC, datetime
from pathlib import PurePosixPath

from errors import InvalidInput
from llm import ModelClient
from models import Candidate, Index, Scope

SYSTEM = """You turn a request for a presentation into a search scope.

Return the scope and nothing else. Do not decide what matters or what belongs on a slide;
that is decided later, from evidence you cannot see here.

since, until: the time window the request implies. Leave both out if it implies none.
paths: file or directory fragments the request names. Leave out if it names none.
keywords: distinctive terms worth matching against code and commit messages. Ordinary
  words - update, work, stuff, things - are not keywords.
audience: who the request says the deck is for, if it says at all.
slide_budget: how many slides were asked for, or the stated default if the request is silent."""


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _validated(proposed: Scope, index: Index) -> Scope:
    """Asserted scope, checked against derived facts before anything downstream trusts it."""
    if proposed.since and proposed.until and _aware(proposed.since) > _aware(proposed.until):
        raise InvalidInput("The request's time window ends before it starts")
    if (proposed.since or proposed.until) and not index.commits:
        raise InvalidInput("This project has no git history, so a time window cannot be applied")

    oldest = min((commit.authored_at for commit in index.commits), default=None)
    if proposed.since and oldest and not index.history_complete and _aware(proposed.since) < oldest:
        raise InvalidInput(
            f"Only the most recent {len(index.commits)} commits are indexed, "
            f"back to {oldest.date().isoformat()}, so that window cannot be answered"
        )

    known = [facts.path for facts in index.files]
    return proposed.model_copy(
        update={"paths": [named for named in proposed.paths if _matches(named, known)]}
    )


def _matches(named: str, known: list[str]) -> bool:
    fragment = named.strip("./")
    return any(fragment in path for path in known)


def _in_window(moment: datetime, scope: Scope) -> bool:
    moment = _aware(moment)
    if scope.since and moment < _aware(scope.since):
        return False
    return not (scope.until and moment > _aware(scope.until))


async def scope(
    client: ModelClient, request: str, *, index: Index, today: datetime, slide_budget: int
) -> Scope:
    proposed = await client.structured(
        f"Today is {today.date().isoformat()}. The default slide count is {slide_budget}.\n\n"
        f"Request: {request}",
        Scope,
        system=SYSTEM,
    )
    return _validated(proposed, index)


def candidates(index: Index, scope: Scope) -> list[Candidate]:
    """Every indexed file the window puts in play, carrying the commits that touched it."""
    touched: dict[str, list[str]] = {}
    for commit in index.commits:
        if not _in_window(commit.authored_at, scope):
            continue
        for path in commit.changes:
            touched.setdefault(path, []).append(commit.sha)

    def candidate(path: str) -> Candidate:
        return Candidate(
            id=path,
            title=PurePosixPath(path).name,
            paths=[path],
            commits=touched.get(path, []),
        )

    indexed = {facts.path for facts in index.files}
    windowed = scope.since or scope.until
    in_play = {path for path in indexed if not windowed or path in touched}
    # A file deleted in the window is still work done, and only git remembers it.
    in_play |= touched.keys() - indexed

    return [candidate(path) for path in sorted(in_play)]


async def gather(
    client: ModelClient, index: Index, request: str, *, today: datetime, slide_budget: int
) -> tuple[Scope, list[Candidate]]:
    settled = await scope(client, request, index=index, today=today, slide_budget=slide_budget)
    return settled, candidates(index, settled)
