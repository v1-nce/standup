from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from standup.core.models import Project, ProjectPaths, Source, SourceKind
from standup.errors import InvalidInput, NotFound, StandupError, Upstream

_SLUG = re.compile(r"[^a-z0-9]+")
_REMOTE = re.compile(r"^(https?://|git@|ssh://)")


def _slug(name: str) -> str:
    return _SLUG.sub("-", name.lower()).strip("-") or "project"


def _identify(name: str, location: str) -> str:
    digest = hashlib.sha256(location.encode()).hexdigest()[:8]
    return f"{_slug(name)}-{digest}"


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

    def create(self, name: str, location: str) -> Project:
        is_remote = bool(_REMOTE.match(location))
        project_id = _identify(name, location)
        paths = self.paths(project_id)
        if paths.root.exists():
            raise InvalidInput(f"{location} is already registered as {project_id}")

        for directory in (paths.root, paths.index, paths.chat, paths.deck):
            directory.mkdir(parents=True)

        try:
            if is_remote:
                _clone(location, paths.clone)
                working_tree = paths.clone
            else:
                working_tree = Path(location).expanduser().resolve()
                if not working_tree.is_dir():
                    raise InvalidInput(f"{location} is not a directory")
        except StandupError:
            shutil.rmtree(paths.root, ignore_errors=True)
            raise

        project = Project(
            id=project_id,
            name=name,
            created_at=datetime.now(UTC),
            source=Source(
                kind=SourceKind.REMOTE if is_remote else SourceKind.LOCAL,
                location=location if is_remote else str(working_tree),
                has_git=(working_tree / ".git").exists(),
            ),
        )
        self._write(paths.root, project)
        return project

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

    def working_tree(self, project_id: str) -> Path:
        project = self.get(project_id)
        if project.source.kind is SourceKind.REMOTE:
            return self.paths(project_id).clone
        return Path(project.source.location)

    def _write(self, root: Path, project: Project) -> None:
        (root / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")

    def _read(self, root: Path) -> Project | None:
        record = root / "project.json"
        if not record.is_file():
            return None
        return Project.model_validate_json(record.read_text(encoding="utf-8"))
