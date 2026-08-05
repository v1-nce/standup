"""Source files → symbols and import tokens. Filters apply during the walk, never after."""

import hashlib
import os
import re
from collections.abc import Iterator
from pathlib import Path

import tree_sitter_language_pack as tsl

from standup.core.models import FileFacts, Symbol

SKIP_DIRS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "out",
    "coverage",
    "__pycache__",
    "site-packages",
    "generated",
    "venv",
    "env",
}
MAX_FILE_BYTES = 1_000_000

_QUOTED = re.compile(r"""["'`]([^"'`\n]+)["'`]""")
_AFTER_KEYWORD = re.compile(r"\b(?:from|use|import|require|include)\b\s+([\w.:/\\@-]+)")
# ESM writes the compiled extension in the specifier: "./util.js" is util.ts on disk.
_SPECIFIER_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")


def walk(root: Path) -> Iterator[Path]:
    """Every file worth indexing. Dotted and vendored directories are pruned, not visited."""
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [
            d for d in subdirectories if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            yield Path(directory) / name


def module_path(statement: str) -> str | None:
    """The module an import names, as a path. Never the symbols it pulls out of that module."""
    quoted = _QUOTED.search(statement)
    named = quoted.group(1) if quoted else None
    if named is None:
        keyword = _AFTER_KEYWORD.search(statement)
        named = keyword.group(1) if keyword else None
    if not named:
        return None

    named = named.replace("::", "/").replace("\\", "/").rstrip("/;")
    for suffix in _SPECIFIER_SUFFIXES:
        if named.endswith(suffix) and len(named) > len(suffix):
            named = named[: -len(suffix)]
            break
    leading = len(named) - len(named.lstrip("."))
    body = named[leading:]
    # A module written with slashes is already a path; only a dotted one needs converting.
    if "/" not in body:
        body = body.replace(".", "/")
    return "." * leading + body.strip("/")


def parse(root: Path) -> list[FileFacts]:
    facts = []
    for path in walk(root):
        language = tsl.detect_language_from_path(str(path))
        if not language or path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            result = tsl.process(
                source,
                tsl.ProcessConfig(
                    language=language,
                    symbols=True,
                    imports=True,
                    structure=False,
                    exports=False,
                    comments=False,
                    docstrings=False,
                    diagnostics=False,
                ),
            )
        except (OSError, UnicodeDecodeError, tsl.Error):
            continue

        imports = []
        for statement in result.imports:
            module = module_path(statement.source)
            if module and module not in imports:
                imports.append(module)

        facts.append(
            FileFacts(
                path=path.relative_to(root).as_posix(),
                content_hash=hashlib.sha256(source.encode()).hexdigest()[:16],
                symbols=[
                    Symbol(name=s.name, kind=str(s.kind), line=s.span.start_line + 1)
                    for s in result.symbols
                ],
                imports=imports,
            )
        )
    return facts
