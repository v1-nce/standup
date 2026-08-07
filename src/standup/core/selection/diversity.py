"""MMR: each pick trades relevance against how much it repeats what is already chosen."""

from pathlib import PurePosixPath

from standup.core.models import Candidate

# Below ~0.5 the deck stops being about the most important work; above ~0.85 it is eight slides
# on one subsystem. 0.7 is the usual starting point and has not been tuned against a benchmark.
LAMBDA = 0.7


def _overlap(left: Candidate, right: Candidate) -> float:
    shared = set(left.commits) & set(right.commits)
    union = set(left.commits) | set(right.commits)
    together = len(shared) / len(union) if union else 0.0
    here = PurePosixPath(left.id).parent.parts[1:]
    there = PurePosixPath(right.id).parent.parts[1:]
    common = sum(1 for a, b in zip(here, there, strict=False) if a == b)
    nearby = common / max(len(here), len(there)) if here or there else 1.0

    return max(together, nearby)


def ordered(candidates: list[Candidate], relevance: dict[str, float], limit: int) -> list[Candidate]:
    """Most worth saying first, each pick discounted by what it repeats. Ties break on id."""
    remaining = sorted(candidates, key=lambda c: (-relevance[c.id], c.id))
    chosen: list[Candidate] = []

    while remaining and len(chosen) < limit:
        # max() keeps the first of equal scores, and `remaining` is already in a settled order.
        best = max(
            remaining,
            key=lambda c: LAMBDA * relevance[c.id]
            - (1 - LAMBDA) * max((_overlap(c, taken) for taken in chosen), default=0.0),
        )
        chosen.append(best)
        remaining.remove(best)

    return chosen
