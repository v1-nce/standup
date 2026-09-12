from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from standup.api.context import router as context_router
from standup.api.decks import router as decks_router
from standup.api.jobs import router as jobs_router
from standup.api.projects import router as projects_router
from standup.api.routes import handle_error
from standup.api.routes import router as system_router
from standup.errors import StandupError

WEB = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="Standup", version="0.2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(projects_router)
app.include_router(context_router)
app.include_router(decks_router)
app.include_router(jobs_router)
app.add_exception_handler(StandupError, handle_error)

if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
