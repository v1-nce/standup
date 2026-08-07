"""PageRank over the import graph. What the rest of the project leans on ranks high."""

import json
from pathlib import Path, PurePosixPath

from standup.core.index.code import walk
from standup.core.models import FileFacts

DAMPING = 0.85
ITERATIONS = 40
TOLERANCE = 1e-9

# A package entry point is named after its directory, not itself.
_ENTRY_POINTS = {"__init__", "index", "mod"}
# Nothing imports a config file or a README, so matching one is always a name collision.
_NOT_IMPORTABLE = {
    ".ini", ".toml", ".cfg", ".json", ".yaml", ".yml", ".xml", ".lock", ".csv",
    ".md", ".rst", ".txt", ".adoc",
}
# Directories an absolute import counts from. Read the project's own config to extend this.
_SOURCE_ROOTS = {"src", "lib", "app"}


def _suffixes(parts: list[str]) -> list[str]:
    """Every trailing run of a path, longest first: a/b/c, b/c, c."""
    return ["/".join(parts[i:]) for i in range(len(parts))]


def _keys(path: str) -> list[str]:
    """The names an import could plausibly use to reach this file."""
    if PurePosixPath(path).suffix.lower() in _NOT_IMPORTABLE:
        return []
    parts = path.rsplit(".", 1)[0].split("/")
    if len(parts) > 1 and parts[-1] in _ENTRY_POINTS:
        parts = parts[:-1]
    return _suffixes(parts)


def _wanted(importer: str, module: str, aliases: dict[str, str]) -> list[str]:
    """The keys an import could mean, best guess first."""
    up = len(module) - len(module.lstrip("."))
    parts = [p for p in module[up:].split("/") if p]

    if not up:
        for depth in range(len(parts), 0, -1):
            declared = aliases.get("/".join(parts[:depth]))
            if declared is not None:
                parts = [*[p for p in declared.split("/") if p], *parts[depth:]]
                break

    if up:
        # Relative: resolved against the importer's own directory, so there is nothing to guess.
        base = list(PurePosixPath(importer).parent.parts)
        climb = up - 1
        if climb:
            base = base[:-climb] if climb <= len(base) else []
        return ["/".join([*base, *parts])]

    # A trailing segment may be the module or the symbol taken from it; try both readings.
    keys = _suffixes(parts) + (_suffixes(parts[:-1]) if len(parts) > 1 else [])
    if len(parts) > 1:
        # `_typeshed/wsgi` is external. Letting it decay to `wsgi` would match any file so named.
        keys = [key for key in keys if "/" in key]
    return keys


def aliases(root: Path) -> dict[str, str]:
    """Package name → the directory it names, as the project's own manifests declare it."""
    declared = {}
    for path in walk(root):
        if path.name != "package.json":
            continue
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("name")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            continue
        if not isinstance(name, str) or not name:
            continue
        directory = path.parent.relative_to(root).as_posix().strip(".")
        source = path.parent / "src"
        if source.is_dir():
            directory = f"{directory}/src" if directory else "src"
        declared[name] = directory
    return declared


def anchors(paths: list[str]) -> list[str]:
    """Prefixes an absolute import resolves against, most specific first. The repo root is one."""
    found = {""}
    for path in paths:
        directories = path.split("/")[:-1]
        for depth, name in enumerate(directories):
            if name in _SOURCE_ROOTS:
                found.add("/".join(directories[: depth + 1]) + "/")
    return sorted(found, key=lambda anchor: (-len(anchor), anchor))


def _nearest(importer: str, candidates: list[str]) -> list[str]:
    """Two files can share a name. The shallowest is the package; a deep copy is a fixture."""
    reachable = [path for path in candidates if path != importer]
    if len(reachable) < 2:
        return reachable
    shallowest = min(path.count("/") for path in reachable)
    return [path for path in reachable if path.count("/") == shallowest]


def edges(files: list[FileFacts], declared: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Importer → imported. An import naming nothing in the project makes no edge."""
    declared = declared or {}
    by_file: dict[str, list[str]] = {}
    by_directory: dict[str, list[str]] = {}
    for facts in files:
        keys = _keys(facts.path)
        if not keys:
            continue
        for key in keys:
            by_file.setdefault(key, []).append(facts.path)
        # Go and Java import a directory, not a file, so every file in it is the target.
        for key in _suffixes(list(PurePosixPath(facts.path).parent.parts)):
            by_directory.setdefault(key, []).append(facts.path)

    rooted = anchors([facts.path for facts in files])
    found = {}
    for facts in files:
        targets = set()
        for module in facts.imports:
            keys = _wanted(facts.path, module, declared)
            if not module.startswith("."):
                # An import written from a source root is exact; only guess once that misses.
                keys = [anchor + module for anchor in rooted] + keys
            for table in (by_file, by_directory):
                hit = next((key for key in keys if key in table), None)
                if hit:
                    targets.update(_nearest(facts.path, table[hit]))
                    break
        found[facts.path] = targets
    return found


def rank(files: list[FileFacts], declared: dict[str, str] | None = None) -> dict[str, float]:
    if not files:
        return {}

    outgoing = edges(files, declared)
    paths = list(outgoing)
    count = len(paths)
    scores = dict.fromkeys(paths, 1.0 / count)

    for _ in range(ITERATIONS):
        incoming = dict.fromkeys(paths, 0.0)
        dangling = 0.0
        for source, targets in outgoing.items():
            if not targets:
                dangling += scores[source]
                continue
            share = scores[source] / len(targets)
            for target in targets:
                incoming[target] += share

        base = (1.0 - DAMPING) / count + DAMPING * dangling / count
        updated = {path: base + DAMPING * incoming[path] for path in paths}
        drift = sum(abs(updated[path] - scores[path]) for path in paths)
        scores = updated
        if drift < TOLERANCE:
            break

    return scores
