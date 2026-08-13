"""Cost, latency and memory for one deck. Cost and latency come from the same real chat turns —
they're the same calls, so one turn reports both — run over the task set in tasks.py. The very
first turn pays for indexing this project cold; that's reported on its own since "time to a new
user's first deck" is a different question from steady state (see open question 2 in CLAUDE.md).
Every task then runs REPEATS times warm, so the reported mean carries a stddev and a range instead
of being one lucky or unlucky sample. Memory is a second, throwaway sequence of projects: index
and select with no model involved, since that's the part whose footprint is supposed to stay flat
as resources grow — and across many projects in one process, to catch anything the process-global
caches in pipeline.py hold onto for longer than they should.

Real usage attaches many resources to one project, not one — so the benchmark does too. Which
resources make up a run comes from test_set.py's RESOURCES, a gitignored list of this machine's
own absolute paths (never committed — see benchmarks/test_set.py). Empty, or missing entirely,
falls back to this repo alone, so the benchmark still runs with zero setup.

    python -m benchmarks.benchmark [path]   (overrides RESOURCES with one path; defaults to standup's own repo)

The cost/latency turns need a real ANTHROPIC_API_KEY or GEMINI_API_KEY in .env; memory does not —
so memory runs first and always reports, even when no key is configured.

Your numbers will vary with API load, exact prompt phrasing and network conditions — run it
yourself rather than trusting a number measured on a different machine, on a different day.
"""

import asyncio
import gc
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
from standup.core.index.docs import IMAGE_MEDIA_TYPES
from standup.core.llm import ModelClient, active_provider, from_settings
from standup.core.models import ChatMessage, Scope
from standup.core.projects import ProjectStore

PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "gemini-flash-lite-latest": (0.10, 0.40),
}

REPEATS = 2  # warm samples per task, after the cold one — a guess, like every other unmeasured
             # constant here (CLAUDE.md § Never measured). Deliberately small: a "new deck" task
             # can cost up to 3 real calls (see CLAUDE.md's call budget table), so REPEATS=3 (10
             # turns, up to 30 calls) measurably exceeded a free-tier Gemini key's 15-req/min cap
             # in testing. Raise it if you're on a paid key and want a tighter spread.
SESSION_PROJECTS = 20  # memory()'s session canary: more than pipeline._INDEX_CACHE's 16-entry cap,
                       # so cache filling up (expected) and an actual leak (still climbing after)
                       # don't look the same on the printout.


def target_paths() -> list[Path]:
    if len(sys.argv) > 1:
        return [Path(sys.argv[1]).expanduser().resolve()]
    if RESOURCES:
        return [Path(p).expanduser().resolve() for p in RESOURCES]
    return [REPO_ROOT]


@contextmanager
def project(paths: list[Path]):
    """A project in a scratch directory, deleted on exit, with every path in `paths` attached —
    a folder or a document, exactly as a real project would take either."""
    with tempfile.TemporaryDirectory(prefix="standup-benchmark-") as home:
        store = ProjectStore(Path(home))
        made = store.create("benchmark")
        for path in paths:
            store.attach_path(made.id, str(path))
        yield store, made.id


async def _turn(
    client: ModelClient, store: ProjectStore, project_id: str, request: str
) -> tuple[float, int, int]:
    """Wall-clock seconds and the token cost of this turn alone, isolated from whatever `client`
    has already accumulated."""
    before = client.input_tokens, client.output_tokens
    history = [ChatMessage(role="user", content=request, at=datetime.now(UTC))]
    started = time.perf_counter()
    await agent.converse(client, store, project_id, history)
    elapsed = time.perf_counter() - started
    return elapsed, client.input_tokens - before[0], client.output_tokens - before[1]


Sample = tuple[float, int, int]


async def _run_tasks(paths: list[Path]) -> tuple[tuple[str, Sample], dict[str, list[Sample]]]:
    """One project, one client for the whole run — matches production's long-lived one. The first
    turn ever made pays for the cold merge (see pipeline._merge's cache) and is reported alone;
    every task then runs REPEATS times warm, interleaved rather than back-to-back, closer to how
    turns actually arrive in a session."""
    client = from_settings()
    try:
        with project(paths) as (store, project_id):
            names = list(TASKS)
            cold = (names[0], await _turn(client, store, project_id, TASKS[names[0]]))

            warm: dict[str, list[Sample]] = {name: [] for name in names}
            for _ in range(REPEATS):
                for name, request in TASKS.items():
                    try:
                        warm[name].append(await _turn(client, store, project_id, request))
                    except Exception as e:
                        print(f"  warm sample for {name!r} failed, skipping: {e}")
            return cold, warm
    finally:
        await client.aclose()


async def _index_and_select(store: ProjectStore, project_id: str) -> None:
    index = await pipeline.indexed(store, project_id)
    pipeline.select(store, project_id, index, "recent work", Scope(slide_budget=5))


def cost_and_latency(paths: list[Path]) -> None:
    model = settings.gemini_model if active_provider() == "gemini" else settings.llm_model
    rate = PRICING.get(model)
    images = [p.name for p in paths if p.is_file() and p.suffix.lower() in IMAGE_MEDIA_TYPES]
    if images:
        print(
            f"note: {', '.join(images)} attached as image resource(s) — description spend during "
            "indexing is a separate, cached, one-time cost and is not included below"
        )

    def priced(in_tokens: int, out_tokens: int) -> float | None:
        if not rate:
            return None
        input_rate, output_rate = rate
        return in_tokens * input_rate / 1e6 + out_tokens * output_rate / 1e6

    (cold_name, (cold_elapsed, cold_in, cold_out)), warm = asyncio.run(_run_tasks(paths))
    _print_row(cold_name, cold_elapsed, priced(cold_in, cold_out), suffix="(cold, first deck)")

    elapsed_all, cost_all = [], []
    for name, samples in warm.items():
        if not samples:
            print(f"  {name:20s} no warm samples survived — see failures above")
            continue
        elapsed_samples = [e for e, _, _ in samples]
        costs = [c for c in (priced(i, o) for _, i, o in samples) if c is not None]
        elapsed_all.extend(elapsed_samples)
        cost_all.extend(costs)

        mean_e, sd_e = statistics.mean(elapsed_samples), statistics.pstdev(elapsed_samples)
        avg_cost = statistics.mean(costs) if costs else None
        _print_row(name, mean_e, avg_cost, suffix=f"+/- {sd_e:.2f}s (n={len(elapsed_samples)})")

    if not elapsed_all:
        print("latency: no warm samples survived — every task's repeats failed, see above")
        return
    print(
        f"latency: {statistics.mean(elapsed_all):.2f}s avg, "
        f"{statistics.pstdev(elapsed_all):.2f}s sd, "
        f"{min(elapsed_all):.2f}-{max(elapsed_all):.2f}s range, over {len(elapsed_all)} warm turns"
    )
    if rate:
        print(f"cost: ${statistics.mean(cost_all):.4f} avg ({model}), {len(cost_all)} warm turns")
    else:
        print(f"cost: no pricing on record for {model!r} — add it to PRICING")


def _print_row(name: str, elapsed: float, priced: float | None, *, suffix: str) -> None:
    said_cost = f"${priced:.4f}" if priced is not None else "n/a"
    print(f"  {name:20s} {elapsed:6.2f}s  {suffix}  {said_cost}")


def memory(paths: list[Path]) -> None:
    tracemalloc.start()
    retained = []
    for i in range(SESSION_PROJECTS):
        with project(paths) as (store, project_id):
            asyncio.run(_index_and_select(store, project_id))
        if i == 0:
            _, peak = tracemalloc.get_traced_memory()
            print(f"memory: {peak / 1_000_000:.1f} MB peak (Python-level allocations, cold build)")
        gc.collect()
        current, _ = tracemalloc.get_traced_memory()
        retained.append(current / 1_000_000)
        print(f"  session, project {i + 1:2d}: {retained[-1]:6.1f} MB retained")
    tracemalloc.stop()

    growth = retained[-1] - retained[0]
    print(
        f"session growth: {growth:+.1f} MB over {SESSION_PROJECTS} projects in one process "
        "(some rise then flat is expected while pipeline's 16-entry index cache fills; still "
        "climbing at the end would point at an actual leak, not this)"
    )


def main() -> None:
    paths = target_paths()
    memory(paths)
    cost_and_latency(paths)


if __name__ == "__main__":
    main()
