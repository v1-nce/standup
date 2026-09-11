"""MMR: each pick trades relevance against how much it repeats what is already chosen."""

import itertools
from pathlib import PurePosixPath

from standup.core.models import Candidate
from standup.core.selection.signals import normalised

# `ordered` normalises relevance to 0-1 before this is applied, since `relevance()`'s raw sum runs
# 0-5.1 and would otherwise make the 1-LAMBDA term worth under 6% of the scale regardless of LAMBDA's
# value - a real unit bug, fixed 2026-08-14 (docs/LOG.md).
#
# LAMBDA itself was re-measured the same day against 3 real quality-benchmark cases (matplotlib,
# twisted, puppet - see benchmarks/quality_cases/) once the scale was correct: 0.7 dropped average
# recall from 30% to 14%. Directory-proximity is a weak diversity signal - real architectures often
# concentrate in one directory, and pushing away from it is wrong exactly when that's true. 0.95
# (diversity nearly off) matched the pre-fix behaviour's recall on all 3 cases, so this is the
# measured value, not a guess reinstated. It should fall again once a better diversity signal exists
# (tracked in docs/LOG.md) - directory proximity was never the right proxy for
# "redundant coverage," at any weight.
LAMBDA = 0.95


def _overlap(left: Candidate, right: Candidate) -> float:
    """How much picking both would repeat one idea, from how deep a directory they share within
    their resource. Two files a commit touched together used to count here too, on the theory that
    shared authorship means shared coverage - it's the opposite: a commit spanning several files is
    one change, and splitting it across slides is a worse deck, not a more diverse one."""
    left_parts = PurePosixPath(left.id).parent.parts
    right_parts = PurePosixPath(right.id).parent.parts
    if left_parts[:1] != right_parts[:1]:
        return 0.0

    here, there = left_parts[1:], right_parts[1:]
    if not here and not there:
        # Both sit at their resource's root. There is no directory to compare, which is an absence
        # of evidence, not evidence of sameness - two unrelated root files (README.md, Dockerfile)
        # used to score as maximally redundant simply because neither had a subdirectory.
        return 0.0
    matched = itertools.takewhile(lambda pair: pair[0] == pair[1], zip(here, there))
    return sum(1 for _ in matched) / max(len(here), len(there))


def ordered(candidates: list[Candidate], relevance: dict[str, float], limit: int) -> list[Candidate]:
    """Most worth saying first, each pick discounted by what it repeats. The first pick breaks a
    tie on id; a later pick favors whichever the initial relevance sort placed first."""
    scaled = normalised(relevance)
    remaining = sorted(candidates, key=lambda c: (-scaled[c.id], c.id))
    chosen: list[Candidate] = []

    while remaining and len(chosen) < limit:
        best = max(
            remaining,
            key=lambda c: LAMBDA * scaled[c.id]
            - (1 - LAMBDA) * max((_overlap(c, taken) for taken in chosen), default=0.0),
        )
        chosen.append(best)
        remaining.remove(best)

    return chosen
