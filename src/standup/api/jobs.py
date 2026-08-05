"""Work that outlives its request. In-process, because the state of record is already on disk."""

import asyncio
from collections.abc import Coroutine
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from standup.errors import Busy, NotFound, StandupError

router = APIRouter(prefix="/jobs", tags=["jobs"])


class Job(BaseModel):
    id: str
    state: Literal["running", "done", "failed"]
    step: str
    detail: str | None = None


_JOBS: dict[str, Job] = {}
_LIVE: dict[str, asyncio.Task[None]] = {}


async def _run(job: Job, work: Coroutine[None, None, None]) -> None:
    try:
        await work
        job.state = "done"
    except StandupError as failure:
        job.state, job.detail = "failed", str(failure)
    except Exception as failure:  # noqa: BLE001 - a job stuck on "running" is worse than a message
        job.state, job.detail = "failed", f"{type(failure).__name__}: {failure}"


def start(project_id: str, step: str, work: Coroutine[None, None, None]) -> Job:
    """One job per project: a second turn would overwrite the deck the first is still writing."""
    running = _LIVE.get(project_id)
    if running and not running.done():
        work.close()
        raise Busy(f"{project_id} is already working")

    job = Job(id=uuid4().hex[:12], state="running", step=step)
    _JOBS[job.id] = job
    _LIVE[project_id] = asyncio.create_task(_run(job, work))
    return job


@router.get("/{job_id}")
def read_job(job_id: str) -> Job:
    if job_id not in _JOBS:
        raise NotFound(f"No job {job_id}")
    return _JOBS[job_id]
