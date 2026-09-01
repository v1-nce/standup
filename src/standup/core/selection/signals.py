"""Free signals over a candidate set. Add one by writing a function and listing it in SIGNALS.

A signal reports only the candidates it has something to say about; anything absent scores 0.
"""

import math
import re
from collections.abc import Callable

from standup.core.models import Candidate, Commit, Index, Scope

Signal = Callable[[list[Candidate], Index, Scope], dict[str, float]]


def _commits(candidate: Candidate, by_sha: dict[str, Commit]) -> list[Commit]:
    return [by_sha[sha] for sha in candidate.commits if sha in by_sha]


def _churn(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, float]:
    by_sha = {commit.sha: commit for commit in index.commits}
    sizes = {
        candidate.id: float(
            sum(
                commit.changes.get(path, 0)
                for commit in _commits(candidate, by_sha)
                for path in candidate.paths
            )
        )
        for candidate in candidates
    }
    # log1p, not the raw line count: churn is power-law - one mega-commit or lockfile diff sits
    # orders of magnitude above everything else, and a linear min-max against it pins every real
    # change near 0. The compressed scale still orders the same candidates the same way.
    return {path: math.log1p(size) for path, size in sizes.items() if size}


def _recency(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, float]:
    by_sha = {commit.sha: commit for commit in index.commits}
    latest = {
        candidate.id: max(
            (c.authored_at.timestamp() for c in _commits(candidate, by_sha)), default=0.0
        )
        for candidate in candidates
    }
    return {path: when for path, when in latest.items() if when}


def _centrality(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, float]:
    return {c.id: index.rank[c.id] for c in candidates if c.id in index.rank}


def _emphasis(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, float]:
    return {c.id: index.emphasis[c.id] for c in candidates if c.id in index.emphasis}


def _affinity(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, float]:
    terms = [term.lower() for term in [*scope.keywords, *scope.paths] if term]
    if not terms:
        return {}
    # Bounded the same way `emphasis()` bounds a symbol name: "auth" used to match inside "author".
    # Stemming/synonyms ("login" vs "session.py") is a separate, larger call - not this one.
    patterns = [re.compile(rf"(?<!\w){re.escape(term)}(?!\w)") for term in terms]

    by_sha = {commit.sha: commit for commit in index.commits}
    excerpts = {facts.path: facts.excerpt for facts in index.files if facts.excerpt}
    hits = {}
    for candidate in candidates:
        haystack = " ".join(
            [
                candidate.id,
                *(excerpts.get(path, "") for path in candidate.paths),
                *(c.message for c in _commits(candidate, by_sha)),
            ]
        ).lower()
        found = float(sum(len(pattern.findall(haystack)) for pattern in patterns))
        if found:
            hits[candidate.id] = found
    return hits


SIGNALS: dict[str, Signal] = {
    "churn": _churn,
    "recency": _recency,
    "centrality": _centrality,
    "emphasis": _emphasis,
    "affinity": _affinity,
}


def normalised(raw: dict[str, float]) -> dict[str, float]:
    """Min-max to 0-1. Shared with `diversity.ordered`, which needs relevance on the same scale it
    normalises overlap to - `LAMBDA` only trades them off correctly when both sides are 0-1."""
    if not raw:
        return {}
    low, high = min(raw.values()), max(raw.values())
    if high == low:
        return dict.fromkeys(raw, 1.0)
    return {path: (value - low) / (high - low) for path, value in raw.items()}


def measure(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, dict[str, float]]:
    """Every signal, normalised to 0-1 across the candidate set, keyed by candidate id."""
    scored = {candidate.id: dict.fromkeys(SIGNALS, 0.0) for candidate in candidates}
    for name, signal in SIGNALS.items():
        for path, value in normalised(signal(candidates, index, scope)).items():
            scored[path][name] = value
    return scored
