import os
import re
from contextlib import suppress
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


def model_env_path() -> Path:
    """Where Standup reads model config from — the user's home, so it survives reinstalls."""
    return Path.home() / ".standup" / ".env"


def provider_from_key(key: str) -> str | None:
    """Infer a provider from an API key's shape, or None when it is not recognizable.

    Order matters: Anthropic keys (``sk-ant-``) also start with ``sk-``, so they are checked
    first. Gemini keys start ``AIza``; OpenAI keys start ``sk-`` (``sk-proj-`` included), which
    is also what OpenRouter, Groq, Together, and other OpenAI-compatible gateways issue.
    """
    if not key:
        return None
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("sk-"):
        return "openai"
    return None


# A suggestion list for MODEL_NAME, one ordered list per provider (default first). It is exactly
# that — a suggestion. Standup passes any unknown name through unchanged, so a model not listed
# here (or a custom OpenAI-compatible server's) still works by typing its exact id.
MODEL_CATALOG: dict[str, list[str]] = {
    "anthropic": ["claude-opus-5", "claude-sonnet-5", "claude-haiku-5"],
    "gemini": ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest"],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini"],
}


def _model_signature(name: str) -> str:
    """A model name's identity: lowercase, letters and digits only. ``Gemini 3.6 Flash``,
    ``gemini-3.6-flash`` and ``gemini3.6flash`` all share one signature."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


_MODEL_BY_SIGNATURE = {
    _model_signature(model): model
    for models in MODEL_CATALOG.values()
    for model in models
}


def canonical_model(name: str) -> str:
    """The catalog's spelling of ``name`` when it matches a known model, else ``name`` unchanged.

    The unchanged pass-through is deliberate: it keeps any OpenAI-compatible gateway model (or a
    brand-new model the catalog does not know yet) working by its exact id.
    """
    return _MODEL_BY_SIGNATURE.get(_model_signature(name), name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(model_env_path(), REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # One key for any provider; the provider is inferred from the key itself. This is the only
    # thing a user needs to set.
    model_api_key: str = ""
    # Optional overrides: a specific model, or an OpenAI-compatible endpoint or gateway (Ollama,
    # LM Studio, vLLM, OpenRouter, ...). Empty base URL means the provider's built-in endpoint.
    model_name: str = ""
    model_base_url: str | None = None

    # Explicit provider override — only needed when a key is not recognizable, or to reach a local
    # OpenAI-compatible server that has no key of its own.
    llm_provider: str = ""
    # Deprecated per-provider keys, kept so existing setups keep working.
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # Deprecated aliases of model_name / model_base_url.
    llm_model: str = ""
    llm_base_url: str | None = None

    # A thinking model spends its output budget before answering; 8192 leaves room for the full
    # canvas `write` JSON plus the model's reasoning (see llm/http_client.py's structured retry).
    llm_max_tokens: int = 8192
    llm_max_concurrency: int = 8
    llm_timeout_seconds: float = 120.0
    data_dir: Path = Path.home() / ".standup"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    def api_key_for(self, provider: str) -> str:
        """The key for ``provider`` — the unified MODEL_API_KEY when it matches, else its legacy key."""
        if provider_from_key(self.model_api_key) == provider:
            return self.model_api_key
        return {
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
        }.get(provider, "")

    def model_for(self, default: str) -> str:
        """The model to call: MODEL_NAME, then LLM_MODEL, then the provider's default.

        A known spelling is normalised to the catalog's canonical name, so ``GEMINI FLASH LITE``
        and ``gemini-flash-lite`` both land on ``gemini-flash-lite-latest``; unknown names pass
        through unchanged.
        """
        return canonical_model(self.model_name or self.llm_model or default)

    def base_url_for(self, default: str | None = None) -> str | None:
        """The endpoint: MODEL_BASE_URL, then LLM_BASE_URL, then the provider's built-in default."""
        return self.model_base_url or self.llm_base_url or default


settings = Settings()


def save_model_api_key(key: str) -> None:
    """Persist ``key`` to the user's ``.env`` and apply it to this running process.

    The file is the same one ``Settings`` reads at startup, so the key survives a restart;
    assigning it to ``settings`` here makes it live immediately, without one.
    """
    env_path = model_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        # ponytail: no-op on Windows; POSIX-only, same convention as ~/.ssh.
        os.chmod(env_path.parent, 0o700)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("MODEL_API_KEY="):
            updated.append(f"MODEL_API_KEY={key}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"MODEL_API_KEY={key}")

    staging = env_path.with_name(".env.tmp")
    staging.write_text("\n".join(updated) + "\n", encoding="utf-8")
    staging.replace(env_path)
    with suppress(OSError):
        # ponytail: no-op on Windows (ACLs already restrict by owner); POSIX-only hardening.
        os.chmod(env_path, 0o600)
    settings.model_api_key = key
