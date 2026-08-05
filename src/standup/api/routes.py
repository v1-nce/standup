from functools import lru_cache

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from standup.config import settings
from standup.core import llm
from standup.core.llm import ModelClient
from standup.core.models import Health, ModelCheck, ModelStatus
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
        provider=provider,
        model=settings.gemini_model if provider == "gemini" else settings.llm_model,
        configured=provider is not None,
        via_gateway=settings.llm_base_url is not None,
    )


@router.post("/model/check")
async def model_check() -> ModelCheck:
    reply = await get_client().text("Reply with the single word: ready", max_tokens=256)
    return ModelCheck(ok=True, reply=reply.strip())
