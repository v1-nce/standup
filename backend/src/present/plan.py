"""One call turns a Selection into slide text. One call, because the slides have to agree."""

from errors import Upstream
from llm import ModelClient
from models import Index, Selection, SlidePlan
from present.validate import problems

SYSTEM = """You write the words for slides whose content has already been decided.

You are given one item per slide, in the order they will appear, with the evidence behind each.
Write one slide per item, in that order, reusing its id exactly.

title: a short phrase naming the item. Not a sentence.
bullets: two to four short lines, each saying something the evidence supports.

Never name a file, function or module that is not in the evidence. Do not add slides, drop
slides, reorder them, or remark on anything that was left out. Describe what changed rather
than showing code."""


def _evidence(selection: Selection, index: Index) -> str:
    by_sha = {commit.sha: commit for commit in index.commits}
    blocks = []
    for entry in selection.chosen:
        candidate = entry.candidate
        lines = [f"id: {candidate.id}", f"files: {', '.join(candidate.paths)}"]
        lines += [f"changed: {by_sha[sha].message}" for sha in candidate.commits if sha in by_sha]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _prompt(selection: Selection, index: Index) -> str:
    audience = f"Audience: {selection.scope.audience}\n" if selection.scope.audience else ""
    return (
        f"Request: {selection.request}\n"
        f"{audience}"
        f"Slides: {len(selection.chosen)}\n\n"
        f"{_evidence(selection, index)}"
    )


async def plan(client: ModelClient, selection: Selection, index: Index) -> SlidePlan:
    """Slide text that matches the selection and names nothing the index has never seen."""
    prompt = _prompt(selection, index)
    draft = await client.structured(prompt, SlidePlan, system=SYSTEM)

    faults = problems(draft, selection, index)
    if faults:
        correction = "\n".join(f"- {fault}" for fault in faults)
        draft = await client.structured(
            f"{prompt}\n\nYour previous answer was rejected:\n{correction}",
            SlidePlan,
            system=SYSTEM,
        )
        faults = problems(draft, selection, index)

    if faults:
        raise Upstream("The slide plan could not be grounded: " + "; ".join(faults))
    return draft
