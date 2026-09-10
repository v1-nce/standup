from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path.home() / ".standup" / ".env", REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    # The model to call, in the active provider's naming. Empty means the provider's default, so
    # one knob selects any model behind any provider.
    llm_model: str = ""
    # A thinking model spends its output budget before answering; 8192 leaves room for the full
    # canvas `write` JSON plus the model's reasoning (see llm/http_client.py's structured retry).
    llm_max_tokens: int = 8192
    llm_max_concurrency: int = 8
    llm_timeout_seconds: float = 120.0
    llm_base_url: str | None = None
    data_dir: Path = Path.home() / ".standup"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
