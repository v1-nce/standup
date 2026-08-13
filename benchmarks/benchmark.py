"""Cost, latency and memory for one deck. Cost and latency come from the same real chat turns —
they're the same calls, so one turn reports both — run over the task set in tasks.py and
averaged, so the number isn't just one lucky prompt. Memory is a second, throwaway project: index
and select with no model involved, since that's the part whose footprint is supposed to stay flat
as resources grow.

Real usage attaches many resources to one project, not one — so the benchmark does too. Which
resources make up a run comes from test_set.py's RESOURCES, a gitignored list of this machine's
own absolute paths (never committed — see benchmarks/test_set.py). Empty, or missing entirely,
falls back to this repo alone, so the benchmark still runs with zero setup.

    python -m benchmarks.benchmark [path]   (overrides RESOURCES with one path; defaults to standup's own repo)

The cost/latency turns need a real ANTHROPIC_API_KEY or GEMINI_API_KEY in .env; memory does not.
"""

import asyncio
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.tasks import RESOURCES, TASKS
from standup.config import REPO_ROOT, settings
from standup.core import agent, pipeline
from standup.core.llm import active_provider, from_settings
from standup.core.models import ChatMessage, Scope
from standup.core.projects import ProjectStore

PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "gemini-flash-lite-latest": (0.10, 0.40),
}


def target_paths() -> list[Path]:
    if len(sys.argv) > 1:
        return [Path(sys.argv[1]).expanduser().resolve()]
    if RESOURCES:
        return [Path(p).expanduser().resolve() for p in RESOURCES]
    return [REPO_ROOT]


@contextmanager
def project(paths: list[Path]):
    """A project in a scratch directory, deleted on exit, with every path in `paths` attached."""
    with tempfile.TemporaryDirectory(prefix="standup-benchmark-") as home:
        store = ProjectStore(Path(home))
        made = store.create("benchmark")
        for path in paths:
            store.attach(made.id, str(path))
        yield store, made.id


async def _turn(store: ProjectStore, project_id: str, request: str):
    client = from_settings()
    history = [ChatMessage(role="user", content=request, at=datetime.now(UTC))]
    started = time.perf_counter()
    try:
        await agent.converse(client, store, project_id, history)
    finally:
        elapsed = time.perf_counter() - started
        await client.aclose()
    return elapsed, client


async def _run_tasks(paths: list[Path]) -> list[tuple[str, float, object]]:
    """One project, one turn per task, in order — only the first pays for a cold index."""
    with project(paths) as (store, project_id):
        results = []
        for name, request in TASKS.items():
            elapsed, client = await _turn(store, project_id, request)
            results.append((name, elapsed, client))
        return results


async def _index_and_select(store: ProjectStore, project_id: str) -> None:
    index = await pipeline.indexed(store, project_id)
    pipeline.select(store, project_id, index, "recent work", Scope(slide_budget=5))


def cost_and_latency(paths: list[Path]) -> None:
    model = settings.gemini_model if active_provider() == "gemini" else settings.llm_model
    rate = PRICING.get(model)

    elapsed_all, cost_all = [], []
    for name, elapsed, client in asyncio.run(_run_tasks(paths)):
        cost = None
        if rate:
            input_rate, output_rate = rate
            cost = client.input_tokens * input_rate / 1e6 + client.output_tokens * output_rate / 1e6
            cost_all.append(cost)
        elapsed_all.append(elapsed)
        print(f"  {name:20s} {elapsed:6.2f}s  " + (f"${cost:.4f}" if cost is not None else "n/a"))

    print(f"latency: {statistics.mean(elapsed_all):.2f}s avg over {len(elapsed_all)} tasks")
    if rate:
        print(f"cost: ${statistics.mean(cost_all):.4f} avg ({model})")
    else:
        print(f"cost: no pricing on record for {model!r} — add it to PRICING")


def memory(paths: list[Path]) -> None:
    tracemalloc.start()
    with project(paths) as (store, project_id):
        asyncio.run(_index_and_select(store, project_id))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"memory: {peak / 1_000_000:.1f} MB peak (Python-level allocations)")


def main() -> None:
    paths = target_paths()
    cost_and_latency(paths)
    memory(paths)


if __name__ == "__main__":
    main()
