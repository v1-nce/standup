"""Registered resources → derived facts. Runs on registration and on change, never per deck."""

import hashlib
import shutil
import threading
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from standup.core.index.code import parse, relative, walk
from standup.core.index.docs import MAX_DOC_CHARS, emphasis, prose, read
from standup.core.index.graph import aliases, rank
from standup.core.index.history import commits
from standup.core.models import Commit, Facts, FileFacts, Index
from standup.errors import InvalidInput

FACTS_FILE = "facts.json"
EXCERPT_CHARS = 4_000

_BUILDS: defaultdict[Path, threading.Lock] = defaultdict(threading.Lock)
_BUILDS_GUARD = threading.Lock()


def _lock_on(facts_dir: Path) -> threading.Lock:
    with _BUILDS_GUARD:
        return _BUILDS[facts_dir]


def fingerprint(root: Path) -> str:
    """Cheap enough to run per deck: file stats only, no reads and no parsing."""
    digest = hashlib.sha256()
    for path in sorted(walk(root)):
        stat = path.stat()
        digest.update(f"{relative(root, path)}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()[:16]


def build(root: Path) -> Facts:
    """One resource's facts. A folder is walked; a file attached on its own is read."""
    if root.is_file():
        return _document(root)

    history, complete = commits(root)
    return Facts(
        fingerprint=fingerprint(root),
        built_at=datetime.now(UTC),
        files=parse(root),
        commits=history,
        history_complete=complete,
        aliases=aliases(root),
        text=prose(root),
    )


def _document(path: Path) -> Facts:
    """A lone file has no history and no imports, so its text is the only evidence there is."""
    text = read(path)
    if not text.strip():
        raise InvalidInput(f"{path.name} has no readable text")

    parsed = parse(path)
    facts = parsed[0] if parsed else FileFacts(path=path.name, content_hash=_digest(text))
    return Facts(
        fingerprint=fingerprint(path),
        built_at=datetime.now(UTC),
        files=[facts.model_copy(update={"excerpt": text[:EXCERPT_CHARS]})],
        text=text[:MAX_DOC_CHARS],
    )


def ensure(root: Path, facts_dir: Path) -> Facts:
    """The stored facts if the resource is unchanged, fresh ones otherwise.

    A corrupt cache file is a cache miss, not a user-facing failure - the source it was derived from
    is still right there, so a bad `facts.json` self-heals by rebuilding rather than raising.
    """
    with _lock_on(facts_dir):
        record = facts_dir / FACTS_FILE
        current = fingerprint(root)
        if record.is_file():
            try:
                stored = Facts.model_validate_json(record.read_text(encoding="utf-8"))
            except ValidationError:
                stored = None
            if stored and stored.fingerprint == current:
                return stored

        facts = build(root)
        facts_dir.mkdir(parents=True, exist_ok=True)
        record.write_text(facts.model_dump_json(), encoding="utf-8")
        return facts


def forget(facts_dir: Path) -> None:
    """Drop what was derived from a resource. Waits for a build rather than racing it.

    Resource ids are uuid-suffixed and unique per attach, so this exact `facts_dir` is never
    reused once forgotten — popping its `_BUILDS` entry after releasing the lock can't race a
    future legitimate caller of the same path.
    """
    with _lock_on(facts_dir):
        shutil.rmtree(facts_dir, ignore_errors=True)
    with _BUILDS_GUARD:
        _BUILDS.pop(facts_dir, None)


def merged(parts: Iterable[tuple[str, Facts]]) -> Index:
    """Many resources, one picture. Every path carries the resource it came from, so two
    repositories cannot collide on `src/main.py`, and ranking runs once over the whole set."""
    files: list[FileFacts] = []
    history: list[Commit] = []
    declared: dict[str, str] = {}
    prose_of_all: list[str] = []
    complete = True
    seen: list[str] = []

    for resource_id, part in parts:
        files += [
            facts.model_copy(update={"path": f"{resource_id}/{facts.path}"}) for facts in part.files
        ]
        history += [
            commit.model_copy(
                update={
                    # Two clones of one repository share every sha, and one would overwrite the other.
                    "sha": f"{resource_id}:{commit.sha}",
                    "changes": {f"{resource_id}/{p}": n for p, n in commit.changes.items()},
                }
            )
            for commit in part.commits
        ]
        declared |= {name: f"{resource_id}/{at}" for name, at in part.aliases.items()}
        prose_of_all.append(part.text)
        complete &= part.history_complete
        seen.append(f"{resource_id}:{part.fingerprint}")

    return Index(
        fingerprint=_digest("|".join(sorted(seen))),
        built_at=datetime.now(UTC),
        files=files,
        commits=history,
        history_complete=complete,
        rank=rank(files, declared),
        emphasis=emphasis("\n".join(prose_of_all)[:MAX_DOC_CHARS], files),
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


__all__ = ["EXCERPT_CHARS", "FACTS_FILE", "build", "ensure", "fingerprint", "forget", "merged"]
