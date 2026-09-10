import pytest
from fastapi.testclient import TestClient

from standup.api import routes
from standup.api.app import app
from standup.config import settings
from standup.errors import Upstream


@pytest.fixture
def client():
    routes.get_client.cache_clear()
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_model_status_reflects_settings(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(settings, "llm_base_url", "https://gateway.example")
    assert client.get("/model").json() == {
        "provider": "anthropic",
        "model": "test-model",
        "configured": True,
        "via_gateway": True,
    }


def test_model_status_names_any_provider_and_the_configured_model(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.0-flash-exp")
    reported = client.get("/model").json()
    assert (reported["provider"], reported["model"]) == ("gemini", "gemini-2.0-flash-exp")


def test_check_reports_unconfigured(client, monkeypatch):
    # Every provider must be cleared: one configured key is enough to make this succeed.
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    response = client.post("/model/check")
    assert response.status_code == 503


def test_check_succeeds(client, monkeypatch):
    class Stub:
        async def text(self, *args, **kwargs):
            return " ready\n"

    monkeypatch.setattr(routes, "get_client", lambda: Stub())
    assert client.post("/model/check").json() == {"ok": True, "reply": "ready"}


def test_check_maps_llm_failure_to_502(client, monkeypatch):
    class Stub:
        async def text(self, *args, **kwargs):
            raise Upstream("upstream exploded")

    monkeypatch.setattr(routes, "get_client", lambda: Stub())
    assert client.post("/model/check").status_code == 502
