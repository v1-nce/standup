"""Git history → commits. The record of what actually happened, against which the prompt is a hint."""

import re
import subprocess
from datetime import datetime
from pathlib import Path

from standup.core.models import Commit
from standup.errors import Upstream

MAX_COMMITS = 5000

# Not NUL: Windows refuses a null byte in an argv entry.
_RECORD = "\x1e"
_FIELD = "\x1f"
_FORMAT = f"{_RECORD}%H{_FIELD}%aI{_FIELD}%an{_FIELD}%s"

# `--numstat` renders a rename as `prefix{old => new}suffix` when old and new share an affix, or
# bare `old => new` when they share nothing. Left unresolved, the whole expression reads as one
# fabricated path - real churn credit for the file as it exists today is lost, and a candidate for
# a path that never existed appears in its place.
_BRACE_RENAME = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")
_BARE_RENAME = re.compile(r"^(.*) => (.*)$")


def _resolved_path(path: str) -> str:
    brace = _BRACE_RENAME.match(path)
    if brace:
        prefix, _old, new, suffix = brace.groups()
        return f"{prefix}{new}{suffix}"
    bare = _BARE_RENAME.match(path)
    return bare.group(2) if bare else path


def _numstat(line: str) -> tuple[int, int, str] | None:
    parts = line.split("\t")
    if len(parts) != 3:
        return None
    insertions, deletions, path = parts
    return (
        int(insertions) if insertions.isdigit() else 0,
        int(deletions) if deletions.isdigit() else 0,
        _resolved_path(path),
    )


def commits(root: Path, limit: int = MAX_COMMITS) -> tuple[list[Commit], bool]:
    """Newest first, and whether that is the whole history. One over the limit reveals a cut."""
    if not (root / ".git").exists():
        return [], True

    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            f"--max-count={limit + 1}",
            "--numstat",
            f"--format={_FORMAT}",
        ],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise Upstream(f"git log failed: {result.stderr.strip()}")

    history = []
    for record in result.stdout.split(_RECORD):
        if not record.strip():
            continue
        header, _, body = record.partition("\n")
        sha, authored_at, author, message = header.split(_FIELD)
        changes = [c for c in (_numstat(line) for line in body.splitlines()) if c]
        history.append(
            Commit(
                sha=sha,
                authored_at=datetime.fromisoformat(authored_at),
                author=author,
                message=message,
                changes={path: insertions + deletions for insertions, deletions, path in changes},
            )
        )
    return history[:limit], len(history) <= limit
