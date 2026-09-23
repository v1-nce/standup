from functools import lru_cache

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from standup.config import provider_from_key, save_model_api_key, settings
from standup.core import llm
from standup.core.llm import ModelClient
from standup.core.models import Health, ModelCheck, ModelKey, ModelStatus
from standup.errors import Busy, InvalidInput, NotConfigured, NotFound, Upstream

router = APIRouter()

STATUS = {NotFound: 404, InvalidInput: 400, Busy: 409, NotConfigured: 503, Upstream: 502}


async def handle_error(request: Request, exc: Exception) -> JSONResponse:
    status = next((code for kind, code in STATUS.items() if isinstance(exc, kind)), 500)
    return JSONResponse({"detail": str(exc)}, status_code=status)


@lru_cache(maxsize=1)
def get_client() -> ModelClient:
    return llm.from_settings()


@router.get("/health")
def health() -> Health:
    return Health(status="ok")


@router.get("/model")
def model_status() -> ModelStatus:
    provider = llm.active_provider()
    return ModelStatus(
        provider=provider if provider in llm.PROVIDERS else None,
        model=llm.active_model() or "",
        configured=provider in llm.PROVIDERS,
        via_gateway=bool(settings.model_base_url or settings.llm_base_url),
        models=llm.MODEL_CATALOG.get(provider, []),
    )


@router.post("/model/key")
def set_model_key(body: ModelKey) -> ModelStatus:
    """Save a pasted key to the user's .env and apply it, so first-run setup never opens a file."""
    key = body.api_key.strip()
    if not key:
        raise InvalidInput("Paste a model API key.")
    if provider_from_key(key) is None:
        raise InvalidInput(
            "Could not detect the provider from that key. Use an Anthropic (sk-ant-...), "
            "Gemini (AIza...), or OpenAI (sk-...) key."
        )
    save_model_api_key(key)
    get_client.cache_clear()
    return model_status()


@router.post("/model/check")
async def model_check() -> ModelCheck:
    reply = await get_client().text("Reply with the single word: ready", max_tokens=256)
    return ModelCheck(ok=True, reply=reply.strip())
