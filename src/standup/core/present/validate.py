"""The trust boundary: a plan that drifts from the selection, or names what does not exist, is refused."""

import re
from pathlib import PurePosixPath

from standup.core.index.docs import IMAGE_MEDIA_TYPES
from standup.core.models import Index, Selection, Slide, SlidePlan

_TOKEN = re.compile(r"[A-Za-z0-9_./-]+")
# A call names something this project defines, with or without arguments - `verify(token)` used to
# sail through unchecked while `verify()` was caught, which is backwards: the more specific claim is
# the one worth checking. `deck.save()` names a method on someone else's object, so the leading dot
# is excluded rather than checked against symbols we never indexed. No space before the paren, so
# "Figure (below)" - a parenthetical, not a call - isn't misread as one; nested calls in the
# argument list aren't matched, which is a real bullet's prose, not real code.
_CALL = re.compile(r"(?<![.\w])([A-Za-z_]\w*)\([^()]*\)")


def _named_files(text: str, suffixes: set[str]) -> set[str]:
    """Only tokens carrying an extension the project actually uses. `e.g.` is prose, not a file."""
    return {
        token.removeprefix("./")
        for token in _TOKEN.findall(text)
        if PurePosixPath(token).suffix in suffixes
    }


def _known(named: str, paths: set[str]) -> bool:
    return any(path == named or path.endswith(f"/{named}") for path in paths)


def _known_image(image: str, paths: set[str]) -> bool:
    return image in paths and PurePosixPath(image).suffix.lower() in IMAGE_MEDIA_TYPES


def order_fault(slides: list[Slide], selection: Selection) -> str | None:
    """None once every chosen candidate has exactly one slide, in selection order. Shared by
    `problems()` and `pipeline.render()`, which used to hand-roll the identical check."""
    expected = [entry.candidate.id for entry in selection.chosen]
    actual = [slide.candidate_id for slide in slides if not slide.free]
    if actual == expected:
        return None
    return f"the slides must be exactly {expected}, in that order, but were {actual}"


def problems(plan: SlidePlan, selection: Selection, index: Index) -> list[str]:
    """Everything wrong with a plan. Empty means it can be trusted."""
    order = order_fault(plan.slides, selection)
    return [*([order] if order else []), *slide_problems(plan.slides, index)]


def slide_problems(slides: list[Slide], index: Index) -> list[str]:
    """Grounding faults for the slides being written, without requiring a complete plan. A free
    slide carries no evidence to check by design — the caller already guaranteed its id doesn't
    collide with a real candidate.

    Names are checked against the whole index rather than the slide's own candidate. Nothing
    fabricated passes either way, but scoping it per candidate also rejected true statements — "this
    replaces src/session.py", "now calls verify()" — and a slide that may not refer to anything
    outside its own file can only be written vaguely. Vague was the defect.
    """
    faults = []

    paths = {facts.path for facts in index.files}
    paths |= {path for commit in index.commits for path in commit.changes}
    suffixes = {PurePosixPath(path).suffix for path in paths} - {""}
    symbols = {symbol.name for facts in index.files for symbol in facts.symbols}

    for slide in slides:
        images = [slide.image, *(element.image for element in slide.elements)]
        faults += [
            f"{slide.candidate_id}: there is no attached image {image!r}"
            for image in images
            if image and not _known_image(image, paths)
        ]
        if slide.free:
            continue

        for text in (
            slide.title,
            slide.subtitle,
            *slide.bullets,
            slide.secondary_title,
            *slide.secondary_bullets,
            slide.speaker_notes,
            *(element.text for element in slide.elements if element.kind == "text"),
        ):
            faults += [
                f"{slide.candidate_id}: there is no file {named!r}"
                for named in _named_files(text, suffixes)
                if not _known(named, paths)
            ]
            faults += [
                f"{slide.candidate_id}: there is no {name!r} in this project"
                for name in _CALL.findall(text)
                if name not in symbols
            ]
    return faults
