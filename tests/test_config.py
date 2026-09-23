import stat
import sys
from pathlib import Path

import pytest

from standup.config import (
    MODEL_CATALOG,
    Settings,
    canonical_model,
    provider_from_key,
    save_model_api_key,
)


def test_defaults():
    s = Settings(_env_file=None)
    assert s.model_api_key == ""
    assert s.model_name == ""
    assert s.model_base_url is None
    assert s.llm_model == ""
    assert s.llm_base_url is None
    assert s.anthropic_api_key == ""
    assert s.gemini_api_key == ""
    assert s.openai_api_key == ""


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "sk-ant-key")
    monkeypatch.setenv("MODEL_NAME", "other")
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "3")
    s = Settings(_env_file=None)
    assert s.model_api_key == "sk-ant-key"
    assert s.model_name == "other"
    assert s.llm_max_concurrency == 3


def test_provider_is_inferred_from_the_key():
    assert provider_from_key("sk-ant-api03-x") == "anthropic"
    assert provider_from_key("AIzaSy-x") == "gemini"
    assert provider_from_key("sk-proj-x") == "openai"
    assert provider_from_key("sk-x") == "openai"
    assert provider_from_key("") is None
    assert provider_from_key("ollama") is None


def test_api_key_for_uses_the_unified_key_when_it_matches(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "sk-ant-key")
    s = Settings(_env_file=None)
    assert s.api_key_for("anthropic") == "sk-ant-key"
    assert s.api_key_for("gemini") == ""
    assert s.api_key_for("openai") == ""


def test_api_key_for_falls_back_to_the_legacy_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "legacy")
    s = Settings(_env_file=None)
    assert s.api_key_for("gemini") == "legacy"
    assert s.api_key_for("anthropic") == ""


def test_model_for_prefers_model_name_then_legacy(monkeypatch):
    assert Settings(_env_file=None).model_for("default") == "default"
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    assert Settings(_env_file=None).model_for("default") == "legacy-model"
    monkeypatch.setenv("MODEL_NAME", "new-model")
    assert Settings(_env_file=None).model_for("default") == "new-model"


def test_base_url_for_prefers_model_base_url_then_legacy(monkeypatch):
    assert Settings(_env_file=None).base_url_for("https://default") == "https://default"
    monkeypatch.setenv("LLM_BASE_URL", "https://legacy")
    assert Settings(_env_file=None).base_url_for("https://default") == "https://legacy"
    monkeypatch.setenv("MODEL_BASE_URL", "https://new")
    assert Settings(_env_file=None).base_url_for("https://default") == "https://new"


def test_canonical_model_normalizes_case_and_separators():
    assert canonical_model("GEMINI FLASH LITE LATEST") == "gemini-flash-lite-latest"
    assert canonical_model("gpt4o") == "gpt-4o"
    assert canonical_model("CLAUDE-OPUS-5") == "claude-opus-5"


def test_canonical_model_passes_unknown_names_through():
    assert canonical_model("llama3.1:8b") == "llama3.1:8b"
    assert canonical_model("my-custom-model") == "my-custom-model"


def test_model_for_normalizes_a_known_name(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "GEMINI FLASH LITE LATEST")
    assert Settings(_env_file=None).model_for("whatever") == "gemini-flash-lite-latest"


def test_the_catalog_lists_the_default_first():
    from standup.core import llm

    for name, kind in llm.PROVIDERS.items():
        assert MODEL_CATALOG[name][0] == kind.default_model


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_save_model_api_key_restricts_file_and_dir_permissions(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    save_model_api_key("sk-ant-test")

    env_path = tmp_path / ".standup" / ".env"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(env_path.parent.stat().st_mode) == 0o700
