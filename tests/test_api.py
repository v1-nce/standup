import pytest
from fastapi.testclient import TestClient

from standup import config
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
        "models": ["claude-opus-5", "claude-sonnet-5", "claude-haiku-5"],
    }


def test_model_status_names_any_provider_and_the_configured_model(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.0-flash-exp")
    reported = client.get("/model").json()
    assert (reported["provider"], reported["model"]) == ("gemini", "gemini-2.0-flash-exp")


def test_model_status_detects_the_provider_from_a_unified_key(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "model_api_key", "AIza-x")
    reported = client.get("/model").json()
    assert reported["provider"] == "gemini"
    assert reported["model"] == "gemini-flash-lite-latest"
    assert reported["configured"] is True


def test_check_reports_unconfigured(client, monkeypatch):
    # Every provider must be cleared: one configured key is enough to make this succeed.
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "model_api_key", "")
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


def test_set_model_key_persists_and_applies_it(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "model_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config, "model_env_path", lambda: env_path)

    reported = client.post("/model/key", json={"api_key": "AIza-test-key"}).json()

    assert reported["provider"] == "gemini"
    assert reported["configured"] is True
    assert "MODEL_API_KEY=AIza-test-key" in env_path.read_text(encoding="utf-8")
    assert settings.model_api_key == "AIza-test-key"


def test_set_model_key_replaces_the_old_line_and_keeps_everything_else(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "model_api_key", "")
    env_path = tmp_path / ".env"
    env_path.write_text("MODEL_API_KEY=old\nDATA_DIR=/somewhere\n", encoding="utf-8")
    monkeypatch.setattr(config, "model_env_path", lambda: env_path)

    reported = client.post("/model/key", json={"api_key": "sk-ant-new"}).json()

    assert reported["provider"] == "anthropic"
    text = env_path.read_text(encoding="utf-8")
    assert "MODEL_API_KEY=sk-ant-new" in text
    assert "DATA_DIR=/somewhere" in text
    assert "MODEL_API_KEY=old" not in text


def test_set_model_key_refuses_a_key_it_cannot_place(client, monkeypatch):
    monkeypatch.setattr(settings, "model_api_key", "")
    response = client.post("/model/key", json={"api_key": "not-a-real-key"})
    assert response.status_code == 400


def test_set_model_key_refuses_an_empty_key(client):
    assert client.post("/model/key", json={"api_key": "   "}).status_code == 400
