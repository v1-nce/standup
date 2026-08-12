from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from standup.api import jobs, routes
from standup.api import projects as projects_api
from standup.api.app import app
from standup.core import pipeline
from standup.core.models import Scope
from standup.errors import NotFound
from tests.conftest import Stuck, pdf_saying
from tests.conftest import settled as await_settled


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    # Entered, so every request shares one event loop and a job outlives the call that began it.
    with TestClient(app) as entered:
        yield entered


@pytest.fixture
def empty(client):
    return client.post("/projects", json={"name": "Demo"}).json()["id"]


def settled(client: TestClient, job: dict) -> dict:
    assert job["state"] != "failed", job["detail"]
    for _ in range(200):
        job = client.get(f"/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
    raise AssertionError("the job never finished")


def test_a_new_project_has_nothing_attached(client, empty):
    assert client.get(f"/projects/{empty}/context").json() == []


def test_attaching_a_folder_indexes_it(client, empty, repo):
    accepted = client.post(f"/projects/{empty}/context", json={"locations": [str(repo)]})
    assert accepted.status_code == 202
    assert settled(client, accepted.json())["state"] == "done"

    attached = client.get(f"/projects/{empty}/context").json()
    assert [item["kind"] for item in attached] == ["folder"]
    assert attached[0]["name"] == "repo"


def test_a_folder_and_a_file_can_be_attached_together(client, empty, repo, tmp_path):
    """One request takes both: the folder is referenced, the file copied."""
    note = tmp_path / "notes.md"
    note.write_text("# Notes\nThe Router matters.")

    accepted = client.post(
        f"/projects/{empty}/context", json={"locations": [str(repo), str(note)]}
    )
    assert accepted.status_code == 202
    settled(client, accepted.json())

    attached = client.get(f"/projects/{empty}/context").json()
    assert [(item["kind"], item["name"]) for item in attached] == [
        ("folder", "repo"),
        ("file", "notes.md"),
    ]
    # Copied in, exactly as a dropped file is — the original may be moved or deleted.
    assert Path(attached[1]["location"]).read_text() == note.read_text()
    assert Path(attached[1]["location"]) != note


def test_uploading_documents_keeps_them_and_indexes_them(client, empty):
    accepted = client.post(
        f"/projects/{empty}/context/files",
        files=[
            ("files", ("notes.md", b"# Notes\nThe Router matters.", "text/markdown")),
            ("files", ("spec.pdf", pdf_saying("Standup selects what matters"), "application/pdf")),
        ],
    )
    assert accepted.status_code == 202
    assert settled(client, accepted.json())["state"] == "done"

    assert {item["name"] for item in client.get(f"/projects/{empty}/context").json()} == {
        "notes.md",
        "spec.pdf",
    }


def test_a_file_that_cannot_be_read_is_refused(client, empty):
    refused = client.post(
        f"/projects/{empty}/context/files",
        files=[("files", ("sheet.xlsx", b"a spreadsheet", "application/vnd.ms-excel"))],
    )
    assert refused.status_code == 400
    assert client.get(f"/projects/{empty}/context").json() == []


def test_a_second_attach_is_queued_rather_than_refused(client, empty, repo, tmp_path):
    """Indexing serialises itself, so attaching again mid-index must not come back 409."""
    other = tmp_path / "second"
    (other / "src").mkdir(parents=True)
    (other / "src" / "app.py").write_text("def go():\n    pass\n")

    first = client.post(f"/projects/{empty}/context", json={"locations": [str(repo)]})
    second = client.post(f"/projects/{empty}/context", json={"locations": [str(other)]})

    assert (first.status_code, second.status_code) == (202, 202)
    settled(client, first.json())
    settled(client, second.json())
    assert {item["name"] for item in client.get(f"/projects/{empty}/context").json()} == {
        "repo",
        "second",
    }


def test_two_documents_with_one_name_both_attach(client, empty):
    accepted = client.post(
        f"/projects/{empty}/context/files",
        files=[
            ("files", ("README.md", b"# Standup", "text/markdown")),
            ("files", ("README.md", b"# Forge", "text/markdown")),
        ],
    )
    assert accepted.status_code == 202
    settled(client, accepted.json())
    assert [item["name"] for item in client.get(f"/projects/{empty}/context").json()] == [
        "README.md",
        "README.md",
    ]


def test_the_identical_document_twice_is_refused(client, empty):
    upload = ("files", ("notes.md", b"# Notes", "text/markdown"))
    settled(client, client.post(f"/projects/{empty}/context/files", files=[upload]).json())

    refused = client.post(f"/projects/{empty}/context/files", files=[upload])
    assert refused.status_code == 400
    assert "already attached" in refused.json()["detail"]


def test_one_refusal_leaves_the_whole_selection_unattached(client, empty, repo, tmp_path):
    """Picking ten things and having the third refused must not attach the first two."""
    note = tmp_path / "notes.md"
    note.write_text("# Notes")

    refused = client.post(
        f"/projects/{empty}/context",
        json={"locations": [str(repo), str(note), str(repo / "src")]},
    )

    assert refused.status_code == 400
    assert client.get(f"/projects/{empty}/context").json() == []


def test_a_folder_that_is_not_there_is_refused(client, empty, tmp_path):
    refused = client.post(f"/projects/{empty}/context", json={"locations": [str(tmp_path / "nope")]})
    assert refused.status_code == 400


def test_removing_context_takes_it_off_the_project(client, empty, repo):
    settled(client, client.post(f"/projects/{empty}/context", json={"locations": [str(repo)]}).json())
    attached = client.get(f"/projects/{empty}/context").json()[0]

    assert client.delete(f"/projects/{empty}/context/{attached['id']}").status_code == 204
    assert client.get(f"/projects/{empty}/context").json() == []


async def test_removing_context_takes_the_deck_it_produced_with_it(client, store, empty, repo):
    settled(client, client.post(f"/projects/{empty}/context", json={"locations": [str(repo)]}).json())
    attached = client.get(f"/projects/{empty}/context").json()[0]
    pipeline.select(
        store, empty, await pipeline.indexed(store, empty), "standup", Scope(slide_budget=2)
    )

    assert client.delete(f"/projects/{empty}/context/{attached['id']}").status_code == 204

    with pytest.raises(NotFound):
        pipeline.read(store, empty)


def test_removing_something_that_was_never_attached_is_404(client, empty):
    assert client.delete(f"/projects/{empty}/context/nope").status_code == 404


async def test_removing_context_is_refused_while_a_turn_is_running(store, monkeypatch, project):
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    stuck = Stuck()
    monkeypatch.setattr(routes, "get_client", lambda: stuck)
    resource_id = project.resources[0].id

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        turn = await async_client.post(f"/projects/{project.id}/chat", json={"content": "go"})
        assert turn.status_code == 202

        refused = await async_client.delete(f"/projects/{project.id}/context/{resource_id}")
        assert refused.status_code == 409

        stuck.released.set()
        job = await await_settled(async_client, turn.json()["id"])
        assert job["state"] == "done"


async def test_removing_context_is_refused_while_indexing_is_in_progress(store, monkeypatch, project):
    """busy() must see indexing too, not only a chat turn — indexing runs unlocked in _LOOSE."""
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    resource_id = project.resources[0].id

    async with (
        jobs.indexing_lock(project.id),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client,
    ):
        refused = await async_client.delete(f"/projects/{project.id}/context/{resource_id}")
        assert refused.status_code == 409
