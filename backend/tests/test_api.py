import pytest
from fastapi.testclient import TestClient

from api import routes
from config import settings
from errors import Upstream
from main import app


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


def test_model_status_names_gemini_and_its_own_model(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(settings, "gemini_model", "gemini-flash-lite-latest")
    reported = client.get("/model").json()
    assert (reported["provider"], reported["model"]) == ("gemini", "gemini-flash-lite-latest")


def test_check_reports_unconfigured(client, monkeypatch):
    # Every provider must be cleared: one configured key is enough to make this succeed.
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
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
