"""Candidates in, an editable Selection out. Pure code - no model reaches this decision."""

from standup.core.models import Candidate, Index, Memory, Scope, Scored, Selection
from standup.core.selection.diversity import ordered
from standup.core.selection.score import WEIGHTS, relevance
from standup.core.selection.signals import measure
from standup.errors import NotFound


def _reason(item_signals: dict[str, float], score: float, cutoff: float | None) -> str:
    """A cut item's own signals and score, already computed - narrated for a human, not derived
    fresh. Ranking itself is unaffected; this only explains a decision already made."""
    dominant = max(item_signals, key=lambda name: WEIGHTS[name] * item_signals[name])
    below = f", {cutoff - score:.2f} below the cutoff" if cutoff is not None else ""
    return f"scored {score:.2f}, mostly from {dominant}{below}"


def choose(
    index: Index,
    scope: Scope,
    candidates: list[Candidate],
    *,
    request: str,
    limit: int | None = None,
    memory: Memory | None = None,
) -> Selection:
    signals = measure(candidates, index, scope, memory)
    scores = {candidate.id: relevance(signals[candidate.id]) for candidate in candidates}

    chosen = ordered(candidates, scores, scope.slide_budget if limit is None else limit)
    taken = {candidate.id for candidate in chosen}
    cutoff = min((scores[c.id] for c in chosen), default=None)

    def scored(candidate: Candidate, *, cut: bool) -> Scored:
        return Scored(
            candidate=candidate,
            signals=signals[candidate.id],
            score=scores[candidate.id],
            reason=_reason(signals[candidate.id], scores[candidate.id], cutoff) if cut else None,
        )

    return Selection(
        request=request,
        scope=scope,
        chosen=[scored(candidate, cut=False) for candidate in chosen],
        cut=[
            scored(candidate, cut=True)
            for candidate in sorted(candidates, key=lambda c: (-scores[c.id], c.id))
            if candidate.id not in taken
        ],
    )


def edited(current: Selection, keep: list[str]) -> Selection:
    """The user's edit, applied literally. Nothing re-ranks, nothing is quietly restored."""
    known = {entry.candidate.id: entry for entry in [*current.chosen, *current.cut]}
    # A repeated id is one item asked for twice, not two: naming it three times used to put the
    # same file on three slides, which python-pptx then renders as three copies of one block.
    wanted = dict.fromkeys(keep)
    unknown = [item for item in wanted if item not in known]
    if unknown:
        raise NotFound(f"This selection has nothing called {unknown}")

    return current.model_copy(
        update={
            "chosen": [known[item] for item in wanted],
            "cut": [entry for item, entry in known.items() if item not in wanted],
        }
    )


__all__ = ["choose", "edited"]
