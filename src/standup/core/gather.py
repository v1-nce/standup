"""What a scope puts in play. Deterministic throughout: the scope itself arrives from agent/."""

from datetime import UTC, datetime
from pathlib import PurePosixPath

from standup.core.index.code import SKIP_DIRS
from standup.core.models import Candidate, Index, Scope
from standup.errors import InvalidInput

# Prose/documentation is indexed (docs.prose reads it for the emphasis signal, grounding still
# knows it) but is never a slide candidate: a deck cites code, not a README or a generated HTML doc.
# html/htm/xhtml catch generated docs (twisted doc/); md/rst/txt/adoc catch READMEs and docs.
NON_CODE_SUFFIXES = {".md", ".rst", ".txt", ".adoc", ".html", ".htm", ".xhtml"}


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def validated(proposed: Scope, index: Index) -> Scope:
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


def _skipped(path: str) -> bool:
    return any(part in SKIP_DIRS for part in PurePosixPath(path).parts[:-1])


def candidates(index: Index, scope: Scope) -> list[Candidate]:
    """Every indexed file the window puts in play, carrying the commits that touched it."""
    touched: dict[str, list[str]] = {}
    for commit in index.commits:
        if not _in_window(commit.authored_at, scope):
            continue
        for path in commit.changes:
            touched.setdefault(path, []).append(commit.sha)

    def candidate(path: str) -> Candidate:
        return Candidate(id=path, paths=[path], commits=touched.get(path, []))

    indexed = {facts.path for facts in index.files}
    windowed = scope.since or scope.until
    in_play = {path for path in indexed if not windowed or path in touched}
    # A file deleted in the window is still work done, and only git remembers it.
    in_play |= touched.keys() - indexed
    in_play = {
        path
        for path in in_play
        if not _skipped(path) and PurePosixPath(path).suffix.lower() not in NON_CODE_SUFFIXES
    }

    return [candidate(path) for path in sorted(in_play)]
