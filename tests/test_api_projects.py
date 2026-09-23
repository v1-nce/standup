import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from standup.api import jobs, routes
from standup.api import projects as projects_api
from standup.api.app import app
from standup.config import settings
from standup.core import index as index_module
from standup.core import pipeline
from standup.core.models import Scope
from standup.core.projects import ProjectStore
from tests.conftest import Stuck, settled


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / "projects")
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    return TestClient(app)


def test_empty_to_begin_with(client):
    assert client.get("/projects").json() == []


def test_create_then_read(client):
    created = client.post("/projects", json={"name": "My App"})
    assert created.status_code == 201
    project_id = created.json()["id"]

    assert [p["id"] for p in client.get("/projects").json()] == [project_id]
    assert client.get(f"/projects/{project_id}").json() == {
        **created.json(),
        "name": "My App",
        "resources": [],
    }


def test_create_without_a_name_is_400(client):
    assert client.post("/projects", json={"name": "  "}).status_code == 400


def test_unknown_project_is_404(client):
    assert client.get("/projects/does-not-exist").status_code == 404
    assert client.delete("/projects/does-not-exist").status_code == 404
    assert client.patch("/projects/does-not-exist", json={"name": "Ghost"}).status_code == 404


def test_rename_keeps_the_id(client):
    project_id = client.post("/projects", json={"name": "Old"}).json()["id"]

    renamed = client.patch(f"/projects/{project_id}", json={"name": "  New  "})
    assert renamed.status_code == 200
    assert renamed.json() == {**renamed.json(), "id": project_id, "name": "New"}
    assert client.get(f"/projects/{project_id}").json()["name"] == "New"


def test_rename_to_nothing_is_400(client):
    project_id = client.post("/projects", json={"name": "Real"}).json()["id"]
    assert client.patch(f"/projects/{project_id}", json={"name": "   "}).status_code == 400


def test_delete(client):
    project_id = client.post("/projects", json={"name": "Temp"}).json()["id"]
    assert client.delete(f"/projects/{project_id}").status_code == 204
    assert client.get("/projects").json() == []


async def test_delete_sweeps_the_in_memory_state_it_touched(tmp_path, monkeypatch):
    """A resource attached and indexed leaves state in four modules' dicts — delete must clear
    all of it, not just the two `detach` already knew about."""
    store = ProjectStore(tmp_path / "projects")
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    project = store.create("Temp")
    note = tmp_path / "notes.md"
    note.write_text("# Notes")
    resource = store.attach_file(project.id, "notes.md", note.read_bytes())
    assert resource.id in store._digests

    facts_dir = store.paths(project.id).index / resource.id
    index_module.ensure(Path(resource.location), facts_dir)
    assert facts_dir in index_module._BUILDS

    index = await pipeline.indexed(store, project.id)
    pipeline.select(store, project.id, index, "standup", Scope(slide_budget=1))
    assert project.id in pipeline._LOCKS
    assert project.id in pipeline._INDEX_CACHE

    projects_api.delete_project(project.id)

    assert resource.id not in store._digests
    assert facts_dir not in index_module._BUILDS
    assert project.id not in pipeline._LOCKS
    assert project.id not in pipeline._INDEX_CACHE


def test_jobs_are_pruned_past_a_cap_but_never_a_running_one(monkeypatch):
    """Mirrors docs._DESCRIBED's bounded-cache test shape: fill past the cap, the oldest
    finished job is dropped, a still-running one never is."""
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_JOBS_MAX", 2)

    jobs._remember(jobs.Job(id="running", state="running", step="s"))
    jobs._remember(jobs.Job(id="done-1", state="done", step="s"))
    jobs._remember(jobs.Job(id="done-2", state="done", step="s"))

    assert set(jobs._JOBS) == {"running", "done-2"}


async def test_delete_is_refused_while_a_turn_is_running(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / "projects")
    project = store.create("Busy")
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    stuck = Stuck()
    monkeypatch.setattr(routes, "get_client", lambda: stuck)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        turn = await client.post(f"/projects/{project.id}/chat", json={"content": "go"})
        assert turn.status_code == 202

        refused = await client.delete(f"/projects/{project.id}")
        assert refused.status_code == 409

        stuck.released.set()
        job = await settled(client, turn.json()["id"])
        assert job["state"] == "done"


async def test_delete_is_refused_while_a_turn_is_starting(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / "projects")
    project = store.create("Starting")
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    monkeypatch.setattr(routes, "get_client", lambda: Stuck())
    entered = threading.Event()
    release = threading.Event()
    real_chat = projects_api._chat

    def delayed_chat(project_id):
        entered.set()
        release.wait(timeout=5)
        return real_chat(project_id)

    monkeypatch.setattr(projects_api, "_chat", delayed_chat)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        sending = asyncio.create_task(
            client.post(f"/projects/{project.id}/chat", json={"content": "go"})
        )
        await asyncio.to_thread(entered.wait, 5)

        refused = await client.delete(f"/projects/{project.id}")
        assert refused.status_code == 409

        release.set()
        turn = await sending
        assert turn.status_code == 202


def test_chat_starts_empty(client):
    project_id = client.post("/projects", json={"name": "Chatty"}).json()["id"]
    assert client.get(f"/projects/{project_id}/chat").json() == []


def test_sending_a_message_without_a_model_is_refused_before_it_is_logged(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "model_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    routes.get_client.cache_clear()

    project_id = client.post("/projects", json={"name": "Quiet"}).json()["id"]

    assert client.post(f"/projects/{project_id}/chat", json={"content": "hi"}).status_code == 503
    assert client.get(f"/projects/{project_id}/chat").json() == []
