import httpx
import pytest

from standup.api import jobs, routes
from standup.api import projects as projects_api
from standup.api.app import app
from standup.core.agent import Turn
from standup.core.agent.commands import Select, Write
from standup.core.models import Scope, Slide, VisualElement
from standup.core.projects import ChatLog
from standup.errors import Upstream
from tests.conftest import settled


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
                            Slide(
                                candidate_id=item,
                                title="Router",
                                bullets=["one"],
                                elements=[
                                    VisualElement(
                                        id="title", kind="text", x=0, y=0, width=100, height=100, text="Router"
                                    )
                                ],
                            )
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
        assert history[0]["role"] == "user"
        assert history[-1]["role"] == "assistant"
        assert history[-1]["content"] == "One slide on the router."
        # Every command the turn actually ran is now on record too, not just the model's own claim.
        assert all(m["role"] == "command" for m in history[1:-1])
        assert history[1:-1], "a turn that wrote a deck ran no commands worth persisting?"

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


async def test_the_users_message_is_visible_immediately_after_the_202(wired, project):
    """The append happens synchronously before send_message returns — a GET /chat racing the
    202, before the job has even started running, must never miss the message that started it."""
    async with wired as client:
        accepted = await client.post(
            f"/projects/{project.id}/chat", json={"content": "standup tomorrow"}
        )
        assert accepted.status_code == 202

        history = (await client.get(f"/projects/{project.id}/chat")).json()
        assert [m["role"] for m in history] == ["user"]
        assert history[0]["content"] == "standup tomorrow"

        await settled(client, accepted.json()["id"])


async def test_the_users_message_is_logged_before_the_turn_is_scheduled(wired, store, monkeypatch, project):
    real_start = jobs.start

    def assert_logged_then_start(step, work, *, lock=None):
        try:
            history = ChatLog(store.paths(project.id).chat).read()
            assert [(message.role, message.content) for message in history] == [
                ("user", "standup tomorrow")
            ]
        except Exception:
            work.close()
            raise
        return real_start(step, work, lock=lock)

    monkeypatch.setattr(jobs, "start", assert_logged_then_start)

    async with wired as client:
        accepted = await client.post(
            f"/projects/{project.id}/chat", json={"content": "standup tomorrow"}
        )
        assert accepted.status_code == 202
        await settled(client, accepted.json()["id"])


async def test_a_second_message_while_one_is_running_is_refused(wired):
    async with wired as client:
        created = await client.post("/projects", json={"name": "Busy"})
        project_id = created.json()["id"]

        first = await client.post(f"/projects/{project_id}/chat", json={"content": "one"})
        second = await client.post(f"/projects/{project_id}/chat", json={"content": "two"})

        assert first.status_code == 202
        assert second.status_code == 409
        assert project_id not in second.json()["detail"]
        await settled(client, first.json()["id"])


async def test_an_unknown_job_is_not_found(wired):
    async with wired as client:
        assert (await client.get("/jobs/nosuchjob")).status_code == 404


class Flaky:
    """A model that always fails partway through the turn."""

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        raise Upstream("rate limited")


async def test_a_failed_turn_still_closes_the_log_instead_of_orphaning_the_message(store, monkeypatch, project):
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    monkeypatch.setattr(routes, "get_client", Flaky)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        accepted = await client.post(f"/projects/{project.id}/chat", json={"content": "standup"})
        job = await settled(client, accepted.json()["id"])
        assert job["state"] == "failed"

        history = (await client.get(f"/projects/{project.id}/chat")).json()
        assert [m["role"] for m in history] == ["user", "assistant"]
        assert "rate limited" in history[1]["content"]


class Broken:
    """A model call that fails with something other than a `StandupError` - the shape of an
    unexpected bug in the client itself, not a mapped provider failure."""

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        raise RuntimeError("boom")


async def test_a_genuinely_unexpected_failure_still_closes_the_log(store, monkeypatch, project):
    """`_turn`'s except was only ever exercised with a `StandupError` (`Flaky`, above) - nothing drove
    a plain, unmapped exception through the same catch."""
    monkeypatch.setattr(projects_api, "get_store", lambda: store)
    monkeypatch.setattr(routes, "get_client", Broken)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        accepted = await client.post(f"/projects/{project.id}/chat", json={"content": "standup"})
        job = await settled(client, accepted.json()["id"])
        assert job["state"] == "failed"

        history = (await client.get(f"/projects/{project.id}/chat")).json()
        assert [m["role"] for m in history] == ["user", "assistant"]
        assert "RuntimeError: boom" in history[1]["content"]
