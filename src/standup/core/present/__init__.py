"""A Selection becomes a deck. Every function here is deterministic — the words arrive from agent/."""

from standup.core.models import Selection, SlidePlan
from standup.core.present.deck import build
from standup.core.present.evidence import evidence
from standup.core.present.validate import problems
from standup.errors import InvalidInput


def revise(existing: SlidePlan, selection: Selection) -> SlidePlan:
    """An edited selection, applied literally. Dropping and reordering cost no model call."""
    by_id = {slide.candidate_id: slide for slide in existing.slides}
    wanted = [entry.candidate.id for entry in selection.chosen]

    unplanned = [item for item in wanted if item not in by_id]
    if unplanned:
        raise InvalidInput(f"No slide has been written for {unplanned} yet")

    return SlidePlan(slides=[by_id[item] for item in wanted])


__all__ = ["build", "evidence", "problems", "revise"]
