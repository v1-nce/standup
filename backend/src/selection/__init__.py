"""Candidates in, an editable Selection out. Pure code - no model reaches this decision."""

from errors import NotFound
from models import Candidate, Index, Scope, Scored, Selection
from selection.diversity import ordered
from selection.score import relevance
from selection.signals import measure


def choose(index: Index, scope: Scope, candidates: list[Candidate], *, request: str) -> Selection:
    signals = measure(candidates, index, scope)
    scores = {candidate.id: relevance(signals[candidate.id]) for candidate in candidates}

    chosen = ordered(candidates, scores, scope.slide_budget)
    taken = {candidate.id for candidate in chosen}

    def scored(candidate: Candidate) -> Scored:
        return Scored(
            candidate=candidate, signals=signals[candidate.id], score=scores[candidate.id]
        )

    return Selection(
        request=request,
        scope=scope,
        chosen=[scored(candidate) for candidate in chosen],
        cut=[
            scored(candidate)
            for candidate in sorted(candidates, key=lambda c: (-scores[c.id], c.id))
            if candidate.id not in taken
        ],
    )


def edited(current: Selection, keep: list[str]) -> Selection:
    """The user's edit, applied literally. Nothing re-ranks, nothing is quietly restored."""
    known = {entry.candidate.id: entry for entry in [*current.chosen, *current.cut]}
    unknown = [item for item in keep if item not in known]
    if unknown:
        raise NotFound(f"This selection has nothing called {unknown}")

    return current.model_copy(
        update={
            "chosen": [known[item] for item in keep],
            "cut": [entry for item, entry in known.items() if item not in keep],
        }
    )


__all__ = ["choose", "edited"]
