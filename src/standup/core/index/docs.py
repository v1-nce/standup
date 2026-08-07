"""How much the project's own writing dwells on each file. Semantic signal that costs nothing."""

from pathlib import Path

import tree_sitter_language_pack as tsl
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from standup.core.index.code import walk
from standup.core.models import FileFacts
from standup.errors import InvalidInput

DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}
PDF_SUFFIX = ".pdf"
ATTACHABLE = DOC_SUFFIXES | {PDF_SUFFIX}
MAX_DOC_CHARS = 4_000_000
MIN_NAME_LENGTH = 5


def readable(name: str) -> bool:
    """Whether a file attached on its own can be turned into text. Checked before it is kept."""
    suffix = Path(name).suffix.lower()
    return suffix in ATTACHABLE or tsl.detect_language_from_path(name) is not None


def read(path: Path) -> str:
    """A file as text. The one place that knows how to open a kind of document."""
    if path.suffix.lower() == PDF_SUFFIX:
        try:
            return "\n".join(page.extract_text() for page in PdfReader(path).pages)
        except (OSError, PyPdfError, ValueError) as unreadable:
            raise InvalidInput(f"{path.name} could not be read: {unreadable}") from unreadable
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def prose(root: Path) -> str:
    """Everything the project writes about itself. Only prose files — a PDF buried in a
    repository is a binary nobody asked us to open; one attached on its own is read."""
    collected: list[str] = []
    size = 0
    for path in walk(root):
        if path.suffix.lower() not in DOC_SUFFIXES or size >= MAX_DOC_CHARS:
            continue
        text = read(path)
        collected.append(text)
        size += len(text)
    return "\n".join(collected)


def emphasis(text: str, files: list[FileFacts]) -> dict[str, float]:
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
        if mentions:
            rates[facts.path] = mentions / len(names)

    if not rates:
        return {}
    loudest = max(rates.values())
    return {path: rate / loudest for path, rate in rates.items()}
