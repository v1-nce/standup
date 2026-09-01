"""A Selection becomes a deck. Every function here is deterministic — the words arrive from agent/."""

from standup.core.models import SlidePlan
from standup.core.present.deck import build
from standup.core.present.evidence import evidence
from standup.core.present.validate import order_fault, problems, slide_problems
from standup.errors import InvalidInput


def revise(existing: SlidePlan, order: list[str]) -> SlidePlan:
    """An edited order, applied literally. Free ids ride along — same rule: named survives, left
    out is cut. Dropping and reordering cost no model call."""
    by_id = {slide.candidate_id: slide for slide in existing.slides}
    order = list(dict.fromkeys(order))

    unplanned = [item for item in order if item not in by_id]
    if unplanned:
        raise InvalidInput(f"No slide has been written for {unplanned} yet")

    return SlidePlan(design=existing.design, slides=[by_id[item] for item in order])


__all__ = ["build", "evidence", "order_fault", "problems", "revise", "slide_problems"]
