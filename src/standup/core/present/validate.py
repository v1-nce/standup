"""The trust boundary: a plan that drifts from the selection, or names what does not exist, is refused."""

import re
from pathlib import PurePosixPath

from standup.core.models import Index, Selection, Slide, SlidePlan

_TOKEN = re.compile(r"[A-Za-z0-9_./-]+")
_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(\)")


def _named_files(text: str, suffixes: set[str]) -> set[str]:
    """Only tokens carrying an extension the project actually uses. `e.g.` is prose, not a file."""
    return {
        token.removeprefix("./")
        for token in _TOKEN.findall(text)
        if PurePosixPath(token).suffix in suffixes
    }


def _known(named: str, paths: set[str]) -> bool:
    return any(path == named or path.endswith(f"/{named}") for path in paths)


def problems(plan: SlidePlan, selection: Selection, index: Index) -> list[str]:
    """Everything wrong with a plan. Empty means it can be trusted."""
    faults = []

    expected = [entry.candidate.id for entry in selection.chosen]
    actual = [slide.candidate_id for slide in plan.slides]
    if actual != expected:
        faults.append(f"the slides must be exactly {expected}, in that order, but were {actual}")

    return [*faults, *slide_problems(plan.slides, selection, index)]


def slide_problems(slides: list[Slide], selection: Selection, index: Index) -> list[str]:
    """Grounding faults for the slides being written, without requiring a complete plan."""
    faults = []

    paths = {facts.path for facts in index.files}
    paths |= {path for commit in index.commits for path in commit.changes}
    suffixes = {PurePosixPath(path).suffix for path in paths} - {""}
    candidates = {entry.candidate.id: entry.candidate for entry in selection.chosen}

    for slide in slides:
        candidate = candidates.get(slide.candidate_id)
        theirs = set(candidate.paths) if candidate else set()
        symbols = {
            symbol.name
            for facts in index.files
            if candidate and facts.path in theirs
            for symbol in facts.symbols
        }

        for text in (slide.title, *slide.bullets):
            faults += [
                f"{slide.candidate_id}: there is no file {named!r}"
                for named in _named_files(text, suffixes)
                if not _known(named, theirs)
            ]
            faults += [
                f"{slide.candidate_id}: there is no {name!r} in this project"
                for name in _CALL.findall(text)
                if name not in symbols
            ]
    return faults
