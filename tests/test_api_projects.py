import pytest
from fastapi.testclient import TestClient

from standup.api import projects as projects_api
from standup.api import routes
from standup.api.app import app
from standup.config import settings
from standup.core.projects import ProjectStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / "projects")
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    return TestClient(app)


@pytest.fixture
def codebase(tmp_path):
    path = tmp_path / "repo"
    (path / ".git").mkdir(parents=True)
    return path


def test_empty_to_begin_with(client):
    assert client.get("/projects").json() == []


def test_create_then_read(client, codebase):
    created = client.post("/projects", json={"name": "My App", "location": str(codebase)})
    assert created.status_code == 201
    project_id = created.json()["id"]

    assert [p["id"] for p in client.get("/projects").json()] == [project_id]
    assert client.get(f"/projects/{project_id}").json()["name"] == "My App"


def test_bad_location_is_400(client, tmp_path):
    response = client.post("/projects", json={"name": "Ghost", "location": str(tmp_path / "nope")})
    assert response.status_code == 400


def test_unknown_project_is_404(client):
    assert client.get("/projects/does-not-exist").status_code == 404
    assert client.delete("/projects/does-not-exist").status_code == 404
    assert client.patch("/projects/does-not-exist", json={"name": "Ghost"}).status_code == 404


def test_rename_keeps_the_id(client, codebase):
    project_id = client.post(
        "/projects", json={"name": "Old", "location": str(codebase)}
    ).json()["id"]

    renamed = client.patch(f"/projects/{project_id}", json={"name": "  New  "})
    assert renamed.status_code == 200
    assert renamed.json() == {**renamed.json(), "id": project_id, "name": "New"}
    assert client.get(f"/projects/{project_id}").json()["name"] == "New"


def test_rename_to_nothing_is_400(client, codebase):
    project_id = client.post(
        "/projects", json={"name": "Real", "location": str(codebase)}
    ).json()["id"]
    assert client.patch(f"/projects/{project_id}", json={"name": "   "}).status_code == 400


def test_delete(client, codebase):
    project_id = client.post(
        "/projects", json={"name": "Temp", "location": str(codebase)}
    ).json()["id"]
    assert client.delete(f"/projects/{project_id}").status_code == 204
    assert client.get("/projects").json() == []


def test_chat_starts_empty(client, codebase):
    project_id = client.post(
        "/projects", json={"name": "Chatty", "location": str(codebase)}
    ).json()["id"]
    assert client.get(f"/projects/{project_id}/chat").json() == []


def test_sending_a_message_without_a_model_is_refused_before_it_is_logged(
    client, codebase, monkeypatch
):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    routes.get_client.cache_clear()

    project_id = client.post(
        "/projects", json={"name": "Quiet", "location": str(codebase)}
    ).json()["id"]

    assert client.post(f"/projects/{project_id}/chat", json={"content": "hi"}).status_code == 503
    assert client.get(f"/projects/{project_id}/chat").json() == []
