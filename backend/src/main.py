import uvicorn
from fastapi import FastAPI

from api.decks import router as decks_router
from api.projects import router as projects_router
from api.routes import handle_error
from api.routes import router as system_router
from errors import StandupError

app = FastAPI(title="Standup", version="0.1.0")
app.include_router(system_router)
app.include_router(projects_router)
app.include_router(decks_router)
app.add_exception_handler(StandupError, handle_error)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
