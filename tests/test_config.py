from standup.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_model == "claude-opus-5"
    assert s.llm_base_url is None
    assert s.anthropic_api_key == ""


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "abc")
    monkeypatch.setenv("LLM_MODEL", "other")
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "3")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "abc"
    assert s.llm_model == "other"
    assert s.llm_max_concurrency == 3
