"""Free signals over a candidate set. Add one by writing a function and listing it in SIGNALS.

A signal reports only the candidates it has something to say about; anything absent scores 0.
"""

import math
import re
from collections.abc import Callable

from standup.core.models import Candidate, Commit, Index, Memory, Scope

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


PATH_MATCH_WEIGHT = 5.0


def _affinity(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, float]:
    terms = [term.lower() for term in [*scope.keywords, *scope.paths] if term]
    if not terms:
        return {}
    # A filename is often a compound word (selectreactor.py), so a path match lets a term be a
    # whole word OR the suffix of a longer name; the right boundary still stops "auth" matching
    # "author". Content stays bounded on both sides, so a keyword never lights up an unrelated word.
    path_patterns = [re.compile(rf"{re.escape(term)}(?!\w)") for term in terms]
    content_patterns = [re.compile(rf"(?<!\w){re.escape(term)}(?!\w)") for term in terms]

    by_sha = {commit.sha: commit for commit in index.commits}
    excerpts = {facts.path: facts.excerpt for facts in index.files if facts.excerpt}
    hits = {}
    for candidate in candidates:
        path_hits = sum(len(pattern.findall(candidate.id.lower())) for pattern in path_patterns)
        content = " ".join(
            [
                *(excerpts.get(path, "") for path in candidate.paths),
                *(c.message for c in _commits(candidate, by_sha)),
            ]
        ).lower()
        content_hits = sum(len(pattern.findall(content)) for pattern in content_patterns)
        # A path match means the file is named after the concept - far stronger than a mere
        # mention in a commit message. log1p on both sides keeps one keyword-rich changelog from
        # flattening every real file to zero (the same compression `_churn` already uses).
        found = math.log1p(path_hits) * PATH_MATCH_WEIGHT + math.log1p(content_hits)
        if found:
            hits[candidate.id] = found
    return hits


def _preference(candidates: list[Candidate], memory: Memory) -> dict[str, float]:
    """The project's own editorial history as a signal. Latest decision wins per candidate: kept
    most recently scores +1, cut most recently -1, unseen 0. `measure` min-max normalises these like
    every other signal, so the relative order is kept > unseen > cut - history nudges ranking but
    never overrides the current request."""
    latest: dict[str, float] = {}
    for entry in memory.entries:
        for item in entry.kept:
            latest[item] = 1.0
        for item in entry.cut:
            latest[item] = -1.0
    return {candidate.id: latest.get(candidate.id, 0.0) for candidate in candidates}


def _no_memory(candidates: list[Candidate], index: Index, scope: Scope) -> dict[str, float]:
    """The SIGNALS slot for a project with no trace yet: nothing to say, so every candidate scores
    the same 0.0 an absent signal would. `measure` swaps in `_preference` once a trace exists."""
    return {}


SIGNALS: dict[str, Signal] = {
    "churn": _churn,
    "recency": _recency,
    "centrality": _centrality,
    "emphasis": _emphasis,
    "affinity": _affinity,
    "memory": _no_memory,
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


def measure(
    candidates: list[Candidate], index: Index, scope: Scope, memory: Memory | None = None
) -> dict[str, dict[str, float]]:
    """Every signal, normalised to 0-1 across the candidate set, keyed by candidate id."""
    scored = {candidate.id: dict.fromkeys(SIGNALS, 0.0) for candidate in candidates}
    for name, signal in SIGNALS.items():
        for path, value in normalised(signal(candidates, index, scope)).items():
            scored[path][name] = value
    # The memory signal needs project state the others don't; computed here and normalised the same
    # way, so it stays a visible, weighted signal rather than a hidden ranking tweak.
    if memory is not None and memory.entries:
        for path, value in normalised(_preference(candidates, memory)).items():
            scored[path]["memory"] = value
    return scored
