"""How much the project's own writing dwells on each file. Semantic signal that costs nothing."""

from pathlib import Path

from standup.core.index.code import walk
from standup.core.models import FileFacts

DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}
MAX_DOC_CHARS = 4_000_000
MIN_NAME_LENGTH = 5


def prose(root: Path) -> str:
    collected: list[str] = []
    size = 0
    for path in walk(root):
        if path.suffix.lower() not in DOC_SUFFIXES or size >= MAX_DOC_CHARS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        collected.append(text)
        size += len(text)
    return "\n".join(collected)


def emphasis(root: Path, files: list[FileFacts]) -> dict[str, float]:
    text = prose(root)
    if not text:
        return {}
    lowered = text.lower()

    rates = {}
    for facts in files:
        filename = Path(facts.path).name
        names = [s.name for s in facts.symbols if len(s.name) >= MIN_NAME_LENGTH]
        mentions = sum(text.count(name) for name in names)
        if len(filename) >= MIN_NAME_LENGTH:
            names.append(filename)
            mentions += lowered.count(filename.lower())
        # Mentions per name, not total: otherwise a file only has to be big to look important.
        if mentions:
            rates[facts.path] = mentions / len(names)

    if not rates:
        return {}
    loudest = max(rates.values())
    return {path: rate / loudest for path, rate in rates.items()}
