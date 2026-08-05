"""A Selection becomes a deck: one call for the words, and deterministic work either side of it."""

from pathlib import Path

from errors import InvalidInput
from llm import ModelClient
from models import Index, Selection, SlidePlan
from present.deck import build
from present.plan import plan


async def present(
    client: ModelClient, selection: Selection, index: Index, destination: Path
) -> Path:
    return build(await plan(client, selection, index), destination)


def revise(existing: SlidePlan, selection: Selection) -> SlidePlan:
    """An edited selection, applied literally. Dropping and reordering cost no model call."""
    by_id = {slide.candidate_id: slide for slide in existing.slides}
    wanted = [entry.candidate.id for entry in selection.chosen]

    unplanned = [item for item in wanted if item not in by_id]
    if unplanned:
        raise InvalidInput(f"No slide has been written for {unplanned} yet")

    return SlidePlan(slides=[by_id[item] for item in wanted])


__all__ = ["build", "plan", "present", "revise"]
