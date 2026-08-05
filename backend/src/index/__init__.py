"""Registered resources → derived facts. Runs on registration and on change, never per deck."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from index.code import parse, walk
from index.docs import emphasis
from index.graph import aliases, rank
from index.history import commits
from models import Index

INDEX_FILE = "index.json"


def fingerprint(root: Path) -> str:
    """Cheap enough to run per deck: file stats only, no reads and no parsing."""
    digest = hashlib.sha256()
    for path in sorted(walk(root)):
        stat = path.stat()
        digest.update(f"{path.relative_to(root).as_posix()}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()[:16]


def build(root: Path) -> Index:
    files = parse(root)
    history, complete = commits(root)
    return Index(
        fingerprint=fingerprint(root),
        built_at=datetime.now(UTC),
        files=files,
        commits=history,
        history_complete=complete,
        rank=rank(files, aliases(root)),
        emphasis=emphasis(root, files),
    )


def ensure(root: Path, index_dir: Path) -> Index:
    """The stored index if the working tree is unchanged, a fresh one otherwise."""
    record = index_dir / INDEX_FILE
    current = fingerprint(root)
    if record.is_file():
        stored = Index.model_validate_json(record.read_text(encoding="utf-8"))
        if stored.fingerprint == current:
            return stored

    index = build(root)
    index_dir.mkdir(parents=True, exist_ok=True)
    record.write_text(index.model_dump_json(), encoding="utf-8")
    return index


__all__ = ["INDEX_FILE", "build", "ensure", "fingerprint"]
