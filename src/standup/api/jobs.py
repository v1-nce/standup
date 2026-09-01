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


def already_working() -> Busy:
    """The project id is never shown as text anywhere else in the UI - interpolating it into this
    message only leaked an internal slug into a user-facing error."""
    return Busy("This project is already working")


class Job(BaseModel):
    id: str
    state: Literal["running", "done", "failed"]
    step: str
    detail: str | None = None


_JOBS: dict[str, Job] = {}
_JOBS_MAX = 200
_LIVE: dict[str, asyncio.Task[None]] = {}
_LOOSE: set[asyncio.Task[None]] = set()
_STARTING: defaultdict[str, int] = defaultdict(int)
_INDEXING: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_PENDING_INDEXING: defaultdict[str, int] = defaultdict(int)


def _remember(job: Job) -> None:
    """Bounded like docs._DESCRIBED — evicts the oldest already-finished job, never a running one."""
    _JOBS[job.id] = job
    if len(_JOBS) > _JOBS_MAX:
        stale = next((id_ for id_, other in _JOBS.items() if other.state != "running"), None)
        if stale:
            del _JOBS[stale]


def evict(project_id: str) -> None:
    """Drop a deleted project's in-memory bookkeeping."""
    _LIVE.pop(project_id, None)
    _STARTING.pop(project_id, None)
    _INDEXING.pop(project_id, None)
    _PENDING_INDEXING.pop(project_id, None)


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
        raise already_working()

    job = Job(id=uuid4().hex[:12], state="running", step=step)
    _remember(job)
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
        raise already_working()
    _STARTING[key] += 1
    try:
        yield
    finally:
        _STARTING[key] -= 1


def start_indexing(step: str, key: str, work: Coroutine[None, None, None]) -> Job:
    """Queue indexing and mark the project busy before the response can return. `start(step, ...)`
    is called with no `lock`, so it never refuses - the try/except this used to wrap around it was
    unreachable dead code, per CLAUDE.md's "delete what you replace"."""
    _PENDING_INDEXING[key] += 1

    async def queued() -> None:
        try:
            async with indexing_lock(key):
                await work
        finally:
            _PENDING_INDEXING[key] -= 1

    return start(step, queued())


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
