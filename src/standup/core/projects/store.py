from __future__ import annotations

import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from standup.core.models import Project, ProjectPaths, Source, SourceKind
from standup.errors import InvalidInput, NotFound, StandupError, Upstream

_SLUG = re.compile(r"[^a-z0-9]+")
_REMOTE = re.compile(r"^(https?://|git@|ssh://)")


def _slug(name: str) -> str:
    return _SLUG.sub("-", name.lower()).strip("-") or "project"


def _clone(url: str, destination: Path) -> None:
    result = subprocess.run(
        ["git", "clone", url, str(destination)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise Upstream(f"git clone failed: {result.stderr.strip()}")


class ProjectStore:
    """Projects on disk. One directory per project, the directory is the record."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def paths(self, project_id: str) -> ProjectPaths:
        root = self._root / project_id
        return ProjectPaths(
            root=root,
            index=root / "index",
            chat=root / "chat",
            deck=root / "deck",
            clone=root / "clone",
        )

    def create(self, name: str, location: str | None = None) -> Project:
        """A project is a name and an empty deck. `location` attaches a codebase to it."""
        wanted = name.strip()
        if not wanted:
            raise InvalidInput("A project needs a name")

        project_id = f"{_slug(wanted)}-{uuid4().hex[:8]}"
        paths = self.paths(project_id)
        for directory in (paths.root, paths.index, paths.chat, paths.deck):
            directory.mkdir(parents=True)

        try:
            source = self._attach(location, paths.clone) if location else None
        except StandupError:
            shutil.rmtree(paths.root, ignore_errors=True)
            raise

        project = Project(id=project_id, name=wanted, created_at=datetime.now(UTC), source=source)
        self._write(paths.root, project)
        return project

    def _attach(self, location: str, clone: Path) -> Source:
        if _REMOTE.match(location):
            _clone(location, clone)
            return Source(kind=SourceKind.REMOTE, location=location, has_git=True)

        working_tree = Path(location).expanduser().resolve()
        if not working_tree.is_dir():
            raise InvalidInput(f"{location} is not a directory")
        return Source(
            kind=SourceKind.LOCAL,
            location=str(working_tree),
            has_git=(working_tree / ".git").exists(),
        )

    def list(self) -> list[Project]:
        if not self._root.is_dir():
            return []
        found = [self._read(child) for child in self._root.iterdir() if child.is_dir()]
        return sorted([p for p in found if p], key=lambda p: p.created_at, reverse=True)

    def get(self, project_id: str) -> Project:
        project = self._read(self._root / project_id)
        if project is None:
            raise NotFound(f"No project {project_id}")
        return project

    def rename(self, project_id: str, name: str) -> Project:
        """The id is the directory and stays put; only the display name moves."""
        wanted = name.strip()
        if not wanted:
            raise InvalidInput("A project needs a name")
        project = self.get(project_id).model_copy(update={"name": wanted})
        self._write(self._root / project_id, project)
        return project

    def delete(self, project_id: str) -> None:
        self.get(project_id)
        shutil.rmtree(self._root / project_id)

    def working_tree(self, project_id: str) -> Path | None:
        """None until a codebase is attached — a project can exist with nothing to index."""
        source = self.get(project_id).source
        if source is None:
            return None
        if source.kind is SourceKind.REMOTE:
            return self.paths(project_id).clone
        return Path(source.location)

    def _write(self, root: Path, project: Project) -> None:
        (root / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")

    def _read(self, root: Path) -> Project | None:
        record = root / "project.json"
        if not record.is_file():
            return None
        return Project.model_validate_json(record.read_text(encoding="utf-8"))
