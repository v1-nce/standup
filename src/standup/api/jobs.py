"""Work that outlives its request. In-process, because the state of record is already on disk."""

import asyncio
from collections import defaultdict
from collections.abc import Coroutine
from contextlib import contextmanager
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
_STARTING: defaultdict[str, int] = defaultdict(int)
_INDEXING: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_PENDING_INDEXING: defaultdict[str, int] = defaultdict(int)


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


@contextmanager
def starting(key: str, *, exclusive: bool = False):
    running = _LIVE.get(key)
    if exclusive and ((running is not None and not running.done()) or _STARTING[key] > 0):
        raise Busy(f"{key} is already working")
    _STARTING[key] += 1
    try:
        yield
    finally:
        _STARTING[key] -= 1


def start_indexing(step: str, key: str, work: Coroutine[None, None, None]) -> Job:
    """Queue indexing and mark the project busy before the response can return."""
    _PENDING_INDEXING[key] += 1

    async def queued() -> None:
        try:
            async with indexing_lock(key):
                await work
        finally:
            _PENDING_INDEXING[key] -= 1

    queued_work = queued()
    try:
        return start(step, queued_work)
    except Exception:
        queued_work.close()
        work.close()
        _PENDING_INDEXING[key] -= 1
        raise


def indexing_lock(key: str) -> asyncio.Lock:
    """The lock indexing serialises on — a second attach mid-index queues rather than 409s.
    `busy()` also reads it, so a delete or selection edit mid-index is refused instead of racing."""
    return _INDEXING[key]


def busy(key: str) -> bool:
    """Whether a job is running for this key, or indexing is in progress — the same check `start`
    makes before refusing, plus indexing's own serialising lock."""
    running = _LIVE.get(key)
    return (
        (running is not None and not running.done())
        or _STARTING[key] > 0
        or _PENDING_INDEXING[key] > 0
        or _INDEXING[key].locked()
    )


@router.get("/{job_id}")
def read_job(job_id: str) -> Job:
    if job_id not in _JOBS:
        raise NotFound(f"No job {job_id}")
    return _JOBS[job_id]
