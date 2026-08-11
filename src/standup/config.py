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
    llm_model: str = "claude-opus-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"
    llm_max_tokens: int = 4096
    llm_max_concurrency: int = 8
    llm_timeout_seconds: float = 120.0
    llm_base_url: str | None = None
    data_dir: Path = Path.home() / ".standup"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
