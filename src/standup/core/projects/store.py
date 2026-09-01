from __future__ import annotations

import hashlib
import re
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from standup.core._json import atomic_write, load_json
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


def _unreadable(action: str, target: str, failure: OSError) -> InvalidInput:
    return InvalidInput(f"{target} could not be {action}: {failure}")


class ProjectStore:
    """Projects on disk. One directory per project, the directory is the record."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._guard = threading.RLock()
        self._digests: dict[str, str] = {}

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
            try:
                data = chosen.read_bytes()
            except OSError as failure:
                raise _unreadable("read", location, failure) from failure
            return self.attach_file(project_id, chosen.name, data)
        return self.attach(project_id, location)

    def attach(self, project_id: str, location: str) -> Resource:
        """A folder on this machine. The path is recorded; nothing is copied."""
        try:
            folder = Path(location).expanduser().resolve()
        except OSError as failure:
            raise _unreadable("resolved", location, failure) from failure
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
            held.kind is ResourceKind.FILE
            and held.name == name
            and self._digest_of(held.id, Path(held.location)) == arriving
            for held in project.resources
        ):
            raise InvalidInput(f"{name} is already attached")

        resource_id = _identify(Path(name).stem)
        home = self.paths(project_id).context / resource_id
        home.mkdir(parents=True)
        kept = home / name
        try:
            kept.write_bytes(data)
        except OSError as failure:
            shutil.rmtree(home, ignore_errors=True)
            raise _unreadable("saved", name, failure) from failure

        try:
            if not read(kept).strip():
                raise InvalidInput(f"{name} has no readable text in it")
        except StandupError:
            shutil.rmtree(home, ignore_errors=True)
            raise

        with self._guard:
            self._digests[resource_id] = arriving
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

    def _digest_of(self, resource_id: str, location: Path) -> str:
        """Hashed once per resource per process, not once per resource per attach. The hash
        itself runs outside the guard — it's a file read, not the quick state update the guard
        is for — so one slow hash doesn't stall every other project's request."""
        with self._guard:
            cached = self._digests.get(resource_id)
        if cached is not None:
            return cached
        computed = _digest(location)
        with self._guard:
            return self._digests.setdefault(resource_id, computed)

    def detach(self, project_id: str, resource_id: str) -> None:
        """The resource, its uploaded copy, and everything derived from it."""
        with self._guard:
            project = self.get(project_id)
            held = [item for item in project.resources if item.id != resource_id]
            if len(held) == len(project.resources):
                raise NotFound(f"No resource {resource_id}")
            self._write(self._root / project_id, project.model_copy(update={"resources": held}))
            self._digests.pop(resource_id, None)

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
        """Every resource's own cleanup, the same as `detach` gives one, batched over all of them."""
        project = self.get(project_id)
        paths = self.paths(project_id)
        with self._guard:
            for resource in project.resources:
                self._digests.pop(resource.id, None)
        for resource in project.resources:
            forget(paths.index / resource.id)
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
            try:
                atomic_write(root / "project.json", project.model_dump_json(indent=2))
            except OSError as failure:
                raise _unreadable("saved", project.name, failure) from failure

    def _read(self, root: Path) -> Project | None:
        record = root / "project.json"
        with self._guard:
            if not record.is_file():
                return None
            return load_json(Project, record.read_text(encoding="utf-8"), f"{root.name}'s project record")
