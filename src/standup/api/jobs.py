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
_LOOSE: set[asyncio.Task[None]] = set()


async def _run(job: Job, work: Coroutine[None, None, None]) -> None:
    try:
        await work
        job.state = "done"
    except StandupError as failure:
        job.state, job.detail = "failed", str(failure)
    except Exception as failure:  # noqa: BLE001 - a job stuck on "running" is worse than a message
        job.state, job.detail = "failed", f"{type(failure).__name__}: {failure}"


def start(step: str, work: Coroutine[None, None, None], *, lock: str | None = None) -> Job:
    """`lock` refuses a second job for the same key — a second turn would overwrite the deck the
    first is still writing. Work that serialises itself passes none and is never refused."""
    running = _LIVE.get(lock) if lock else None
    if running and not running.done():
        work.close()
        raise Busy(f"{lock} is already working")

    job = Job(id=uuid4().hex[:12], state="running", step=step)
    _JOBS[job.id] = job
    task = asyncio.create_task(_run(job, work))
    if lock:
        _LIVE[lock] = task
    else:
        _LOOSE.add(task)
        task.add_done_callback(_LOOSE.discard)
    return job


@router.get("/{job_id}")
def read_job(job_id: str) -> Job:
    if job_id not in _JOBS:
        raise NotFound(f"No job {job_id}")
    return _JOBS[job_id]
