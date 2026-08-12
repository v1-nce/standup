"""MMR: each pick trades relevance against how much it repeats what is already chosen."""

import itertools
from pathlib import PurePosixPath

from standup.core.models import Candidate

# Below ~0.5 the deck stops being about the most important work; above ~0.85 it is eight slides
# on one subsystem. 0.7 is the usual starting point and has not been tuned against a benchmark.
LAMBDA = 0.7


def _overlap(left: Candidate, right: Candidate) -> float:
    shared = set(left.commits) & set(right.commits)
    union = set(left.commits) | set(right.commits)
    together = len(shared) / len(union) if union else 0.0
    
    left_parts = PurePosixPath(left.id).parent.parts
    right_parts = PurePosixPath(right.id).parent.parts
    if left_parts[:1] != right_parts[:1]:
        nearby = 0.0
    else:
        here, there = left_parts[1:], right_parts[1:]
        matched = itertools.takewhile(lambda pair: pair[0] == pair[1], zip(here, there))
        common = sum(1 for _ in matched)
        nearby = common / max(len(here), len(there)) if here or there else 1.0

    return max(together, nearby)


def ordered(candidates: list[Candidate], relevance: dict[str, float], limit: int) -> list[Candidate]:
    """Most worth saying first, each pick discounted by what it repeats. The first pick breaks a
    tie on id; a later pick favors whichever the initial relevance sort placed first."""
    remaining = sorted(candidates, key=lambda c: (-relevance[c.id], c.id))
    chosen: list[Candidate] = []

    while remaining and len(chosen) < limit:
        best = max(
            remaining,
            key=lambda c: LAMBDA * relevance[c.id]
            - (1 - LAMBDA) * max((_overlap(c, taken) for taken in chosen), default=0.0),
        )
        chosen.append(best)
        remaining.remove(best)

    return chosen
