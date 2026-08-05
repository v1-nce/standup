"""Fixtures shared by every test that needs a real project on disk."""

import subprocess

import pytest

from standup.core import pipeline
from standup.core.projects import ProjectStore


@pytest.fixture
def repo(tmp_path):
    """A small git repository: a hub, a leaf, a doc that mentions the hub, and one commit."""
    path = tmp_path / "repo"
    (path / "src").mkdir(parents=True)
    (path / "src" / "hub.py").write_text("class Router:\n    pass\n")
    (path / "src" / "leaf.py").write_text("def alone():\n    pass\n")
    (path / "README.md").write_text("The Router matters here.\n")
    for command in (
        ["init", "-q"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "Tester"],
        ["add", "-A"],
        ["commit", "-qm", "first commit"],
    ):
        subprocess.run(["git", "-C", str(path), *command], check=True, capture_output=True)
    return path


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(store, repo):
    return store.create("Demo", str(repo))


@pytest.fixture
async def index(store, project):
    return await pipeline.indexed(store, project.id)
