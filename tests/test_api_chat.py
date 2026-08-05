import asyncio

import httpx
import pytest

from standup.api import projects as projects_api
from standup.api import routes
from standup.api.app import app
from standup.core.agent import Turn
from standup.core.agent.commands import Select, Write
from standup.core.models import Scope, Slide


class Conversation:
    """Selects, writes a slide for whatever was chosen, renders, then reports."""

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        if "DECK\nnone yet" in prompt:
            return Turn(
                reply="",
                commands=[
                    Select(action="select", request="standup", scope=Scope(slide_budget=1))
                ],
            )
        if "[no slide]" in prompt:
            chosen = [
                line.strip().removesuffix(" [no slide]")
                for line in prompt.splitlines()
                if line.endswith("[no slide]")
            ]
            return Turn(
                reply="",
                commands=[
                    Write(
                        action="write",
                        slides=[
                            Slide(candidate_id=item, title="Router", bullets=["one"])
                            for item in chosen
                        ],
                    )
                ],
            )
        return Turn(reply="One slide on the router.")


@pytest.fixture
def wired(store, monkeypatch):
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    monkeypatch.setattr(routes, "get_client", Conversation)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def settled(client: httpx.AsyncClient, job_id: str) -> dict:
    for _ in range(200):
        job = (await client.get(f"/jobs/{job_id}")).json()
        if job["state"] != "running":
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("the job never finished")


async def test_one_message_produces_a_deck_and_a_reply(wired, project):
    async with wired as client:
        project_id = project.id

        accepted = await client.post(
            f"/projects/{project_id}/chat", json={"content": "standup tomorrow"}
        )
        assert accepted.status_code == 202

        job = await settled(client, accepted.json()["id"])
        assert job["state"] == "done", job["detail"]

        history = (await client.get(f"/projects/{project_id}/chat")).json()
        assert [m["role"] for m in history] == ["user", "assistant"]
        assert history[1]["content"] == "One slide on the router."

        deck = (await client.get(f"/projects/{project_id}/deck")).json()
        assert [s["title"] for s in deck["slides"]] == ["Router"]
        assert deck["selection"]["request"] == "standup"

        downloaded = await client.get(f"/projects/{project_id}/deck/file")
        assert downloaded.status_code == 200
        assert downloaded.content[:2] == b"PK"


async def test_a_project_with_no_deck_says_so(wired):
    async with wired as client:
        created = await client.post("/projects", json={"name": "Empty"})
        assert (await client.get(f"/projects/{created.json()['id']}/deck")).status_code == 404


async def test_a_second_message_while_one_is_running_is_refused(wired):
    async with wired as client:
        created = await client.post("/projects", json={"name": "Busy"})
        project_id = created.json()["id"]

        first = await client.post(f"/projects/{project_id}/chat", json={"content": "one"})
        second = await client.post(f"/projects/{project_id}/chat", json={"content": "two"})

        assert first.status_code == 202
        assert second.status_code == 409
        await settled(client, first.json()["id"])


async def test_an_unknown_job_is_not_found(wired):
    async with wired as client:
        assert (await client.get("/jobs/nosuchjob")).status_code == 404
