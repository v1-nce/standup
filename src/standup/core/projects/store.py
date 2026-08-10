from __future__ import annotations

import hashlib
import re
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from standup.core.index import forget
from standup.core.index.docs import read, readable
from standup.core.models import Project, ProjectPaths, Resource, ResourceKind
from standup.errors import InvalidInput, NotFound, StandupError

_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    return _SLUG.sub("-", name.lower()).strip("-") or "item"


def _identify(name: str) -> str:
    """Readable enough to show in a slide, unique enough to survive a rename."""
    return f"{_slug(name)}-{uuid4().hex[:8]}"


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


class ProjectStore:
    """Projects on disk. One directory per project, the directory is the record."""

    def __init__(self, root: Path) -> None:
        self._root = root
        # project.json is read-modify-written from several threads at once, and a reader can
        # otherwise catch it mid-truncation. Re-entrant: every mutator reads before it writes.
        self._guard = threading.RLock()

    def paths(self, project_id: str) -> ProjectPaths:
        root = self._root / project_id
        return ProjectPaths(
            root=root,
            index=root / "index",
            chat=root / "chat",
            deck=root / "deck",
            context=root / "context",
        )

    def create(self, name: str) -> Project:
        """A project is a name and an empty deck. Resources are attached afterwards."""
        wanted = name.strip()
        if not wanted:
            raise InvalidInput("A project needs a name")

        paths = self.paths(_identify(wanted))
        for directory in (paths.root, paths.index, paths.chat, paths.deck, paths.context):
            directory.mkdir(parents=True)

        project = Project(id=paths.root.name, name=wanted, created_at=datetime.now(UTC))
        self._write(paths.root, project)
        return project

    def attach_path(self, project_id: str, location: str) -> Resource:
        """A folder is referenced where it lives; a document is copied in, exactly as an uploaded
        one is, so the two ways of adding a file agree."""
        chosen = Path(location).expanduser()
        if chosen.is_file():
            return self.attach_file(project_id, chosen.name, chosen.read_bytes())
        return self.attach(project_id, location)

    def attach(self, project_id: str, location: str) -> Resource:
        """A folder on this machine. The path is recorded; nothing is copied."""
        folder = Path(location).expanduser().resolve()
        if not folder.is_dir():
            raise InvalidInput(f"{location} is not a directory")

        project = self.get(project_id)
        for held in project.resources:
            if held.kind is not ResourceKind.FOLDER:
                continue
            other = Path(held.location)
            if folder.is_relative_to(other) or other.is_relative_to(folder):
                raise InvalidInput(f"{held.name} already covers {folder}")

        return self._keep(
            project_id,
            Resource(
                id=_identify(folder.name),
                kind=ResourceKind.FOLDER,
                name=folder.name,
                location=str(folder),
                added_at=datetime.now(UTC),
            ),
        )

    def attach_file(self, project_id: str, filename: str, data: bytes) -> Resource:
        """An uploaded document, copied in — the browser never gives us a path to point at."""
        name = Path(filename).name
        if not readable(name):
            raise InvalidInput(f"Standup cannot read {Path(name).suffix or 'that kind of file'} yet")

        project = self.get(project_id)
        arriving = hashlib.sha256(data).hexdigest()
        if any(
            held.kind is ResourceKind.FILE and held.name == name and _digest(Path(held.location)) == arriving
            for held in project.resources
        ):
            raise InvalidInput(f"{name} is already attached")

        resource_id = _identify(Path(name).stem)
        home = self.paths(project_id).context / resource_id
        home.mkdir(parents=True)
        kept = home / name
        kept.write_bytes(data)

        try:
            if not read(kept).strip():
                raise InvalidInput(f"{name} has no readable text in it")
        except StandupError:
            shutil.rmtree(home, ignore_errors=True)
            raise

        return self._keep(
            project_id,
            Resource(
                id=resource_id,
                kind=ResourceKind.FILE,
                name=name,
                location=str(kept),
                added_at=datetime.now(UTC),
            ),
        )

    def detach(self, project_id: str, resource_id: str) -> None:
        """The resource, its uploaded copy, and everything derived from it."""
        with self._guard:
            project = self.get(project_id)
            held = [item for item in project.resources if item.id != resource_id]
            if len(held) == len(project.resources):
                raise NotFound(f"No resource {resource_id}")
            self._write(self._root / project_id, project.model_copy(update={"resources": held}))

        paths = self.paths(project_id)
        shutil.rmtree(paths.context / resource_id, ignore_errors=True)
        forget(paths.index / resource_id)

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

    def _keep(self, project_id: str, resource: Resource) -> Resource:
        """Re-reads inside the lock: the caller's copy is older than a concurrent attach's write."""
        with self._guard:
            project = self.get(project_id)
            held = [*project.resources, resource]
            self._write(self._root / project_id, project.model_copy(update={"resources": held}))
        return resource

    def _write(self, root: Path, project: Project) -> None:
        with self._guard:
            (root / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")

    def _read(self, root: Path) -> Project | None:
        record = root / "project.json"
        with self._guard:
            if not record.is_file():
                return None
            return Project.model_validate_json(record.read_text(encoding="utf-8"))
