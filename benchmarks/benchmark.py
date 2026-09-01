"""Reproducible cost, request latency, and memory measurements for Standup.

Every deck sample gets an isolated project. A cold sample lets `agent.converse()` pay the index
cost; a warm sample pre-indexes the same otherwise-empty project before starting the request clock.
No sample inherits a deck from another sample, so a new-deck prompt is never accidentally measured
as an edit or no-op.

Run `python -m benchmarks.benchmark --help` for controls. API-backed performance samples require a
configured model; memory is deterministic and requires no model for ordinary code/document inputs.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import platform
import sys
import tempfile
import time
import tracemalloc
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from benchmarks.metrics import (
    MB,
    Pricing,
    RssSampler,
    cost_usd,
    distribution,
    linear_slope,
    rss_bytes,
)
from benchmarks.tasks import COLD_TASK, TASKS
from standup.config import REPO_ROOT, settings
from standup.core import agent, pipeline
from standup.core.index.docs import IMAGE_MEDIA_TYPES
from standup.core.llm import ModelClient, active_provider, from_settings
from standup.core.models import ChatMessage, Scope
from standup.core.projects import ChatLog, ProjectStore

T = TypeVar("T", bound=BaseModel)

# Defaults are only used for an exact configured model and are emitted with their provenance.
# CLI overrides exist because provider prices change independently of this repository.
PRICING = {
    "claude-opus-5": Pricing(5.00, 25.00, "https://www.anthropic.com/pricing (recorded 2026-08-14)"),
    "gemini-flash-lite-latest": Pricing(
        0.10, 0.40, "https://ai.google.dev/gemini-api/docs/pricing (recorded 2026-08-14)"
    ),
}


class TrackedClient:
    """A transparent model seam that records each logical call, including failed calls."""

    def __init__(self, inner: ModelClient) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    @property
    def input_tokens(self) -> int:
        return self.inner.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.inner.output_tokens

    async def _measure(self, kind: str, call) -> Any:
        before = self.input_tokens, self.output_tokens
        started = time.perf_counter()
        error = None
        response = None
        try:
            response = await call()
            return response
        except Exception as failure:
            error = f"{type(failure).__name__}: {failure}"
            raise
        finally:
            commands = getattr(response, "commands", None)
            self.calls.append(
                {
                    "kind": kind,
                    "latency_seconds": time.perf_counter() - started,
                    "input_tokens": self.input_tokens - before[0],
                    "output_tokens": self.output_tokens - before[1],
                    "success": error is None,
                    "error": error,
                    "response_type": type(response).__name__ if response is not None else None,
                    "response_changes_deck": getattr(response, "changes_deck", None),
                    "response_commands": (
                        [getattr(command, "action", type(command).__name__) for command in commands]
                        if commands is not None
                        else None
                    ),
                    "response_reply_present": bool(getattr(response, "reply", "")),
                }
            )

    async def text(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        return await self._measure(
            "text", lambda: self.inner.text(prompt, system=system, max_tokens=max_tokens)
        )

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        return await self._measure(
            "structured",
            lambda: self.inner.structured(prompt, schema, system=system, max_tokens=max_tokens),
        )

    async def describe_image(
        self, data: bytes, media_type: str, *, prompt: str, max_tokens: int | None = None
    ) -> str:
        return await self._measure(
            "describe_image",
            lambda: self.inner.describe_image(
                data, media_type, prompt=prompt, max_tokens=max_tokens
            ),
        )

    async def aclose(self) -> None:
        await self.inner.aclose()


@contextmanager
def project(paths: list[Path]):
    """Create and fully dispose one benchmark project, including process-global cache entries."""
    with tempfile.TemporaryDirectory(prefix="standup-benchmark-") as home:
        store = ProjectStore(Path(home))
        made = store.create("benchmark")
        for path in paths:
            store.attach_path(made.id, str(path))
        try:
            yield store, made.id
        finally:
            try:
                store.delete(made.id)
            finally:
                pipeline.evict(made.id)


async def _index_and_select(store: ProjectStore, project_id: str) -> None:
    index = await pipeline.indexed(store, project_id)
    if index is None:
        raise RuntimeError("benchmark project has no index")
    pipeline.select(store, project_id, index, "recent work", Scope(slide_budget=5))


async def _deck_sample(
    client: TrackedClient,
    paths: list[Path],
    task: str,
    request: str,
    temperature: str,
    repeat: int,
) -> dict[str, Any]:
    with project(paths) as (store, project_id):
        if temperature == "warm":
            index = await pipeline.indexed(store, project_id)
            if index is None:
                raise RuntimeError("benchmark project has no index")

        call_offset = len(client.calls)
        history = [ChatMessage(role="user", content=request, at=datetime.now(UTC))]
        started = time.perf_counter()
        error = None
        deck = None
        log = ChatLog(store.paths(project_id).chat)
        try:
            await agent.converse(client, store, project_id, history, log=log)
            deck = pipeline.read(store, project_id)
            if not deck.slides:
                raise RuntimeError("turn completed without producing slides")
        except Exception as failure:  # noqa: BLE001 — every failed attempt belongs in the report
            error = f"{type(failure).__name__}: {failure}"
        elapsed = time.perf_counter() - started
        calls = client.calls[call_offset:]
        input_tokens = sum(call["input_tokens"] for call in calls)
        output_tokens = sum(call["output_tokens"] for call in calls)
        return {
            "task": task,
            "temperature": temperature,
            "repeat": repeat,
            "success": error is None,
            "error": error,
            "latency_seconds": elapsed,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model_calls": len(calls),
            "command_outcomes": [
                message.content for message in log.read() if message.role == "command"
            ],
            "selected_candidates": len(deck.selection.chosen) if deck is not None else 0,
            "written_slides": len(deck.slides or []) if deck is not None else 0,
            "calls": calls,
        }


def _model_name() -> str:
    return settings.gemini_model if active_provider() == "gemini" else settings.llm_model


def _pricing(args: argparse.Namespace, model: str) -> Pricing | None:
    if (args.input_price is None) != (args.output_price is None):
        raise ValueError("--input-price and --output-price must be supplied together")
    if args.input_price is not None:
        return Pricing(args.input_price, args.output_price, "command-line override")
    return PRICING.get(model)


async def performance(paths: list[Path], args: argparse.Namespace) -> dict[str, Any]:
    model = _model_name()
    pricing = _pricing(args, model)
    client = TrackedClient(from_settings())
    samples: list[dict[str, Any]] = []
    try:
        for repeat in range(1, args.repeats + 1):
            name, request = COLD_TASK
            samples.append(await _deck_sample(client, paths, name, request, "cold", repeat))
            if args.delay:
                await asyncio.sleep(args.delay)
            for name, request in TASKS.items():
                samples.append(await _deck_sample(client, paths, name, request, "warm", repeat))
                if args.delay:
                    await asyncio.sleep(args.delay)
    finally:
        await client.aclose()

    for sample in samples:
        sample["cost_usd"] = cost_usd(
            sample["input_tokens"], sample["output_tokens"], pricing
        )

    groups: dict[str, Any] = {}
    for temperature in ("cold", "warm"):
        selected = [sample for sample in samples if sample["temperature"] == temperature]
        successful = [sample for sample in selected if sample["success"]]
        groups[temperature] = {
            "attempted": len(selected),
            "succeeded": len(successful),
            "success_rate": len(successful) / len(selected) if selected else 0.0,
            "deck_latency_seconds": distribution(
                sample["latency_seconds"] for sample in successful
            ),
            "outcome_latency_seconds": distribution(
                sample["latency_seconds"] for sample in selected
            ),
            "successful_deck_cost_usd": distribution(
                sample["cost_usd"] for sample in successful if sample["cost_usd"] is not None
            ),
            "attempt_cost_usd": distribution(
                sample["cost_usd"] for sample in selected if sample["cost_usd"] is not None
            ),
            "failed_cost_usd_total": sum(
                sample["cost_usd"] or 0.0 for sample in selected if not sample["success"]
            ),
            "model_calls": distribution(float(sample["model_calls"]) for sample in selected),
        }

    return {
        "provider": active_provider(),
        "model": model,
        "pricing": (
            {
                "input_per_million": pricing.input_per_million,
                "output_per_million": pricing.output_per_million,
                "source": pricing.source,
            }
            if pricing
            else None
        ),
        "groups": groups,
        "samples": samples,
        "complete": all(sample["success"] for sample in samples),
    }


def memory(paths: list[Path], projects: int) -> dict[str, Any]:
    """Profile index + select and then the real project-deletion lifecycle."""
    gc.collect()
    try:
        baseline_rss = rss_bytes()
    except OSError:
        baseline_rss = None
    tracemalloc.start()
    baseline_python, _ = tracemalloc.get_traced_memory()
    samples: list[dict[str, float | int | None]] = []

    for repeat in range(1, projects + 1):
        tracemalloc.reset_peak()
        with RssSampler() as rss_peak, project(paths) as (store, project_id):
            asyncio.run(_index_and_select(store, project_id))
        gc.collect()
        python_current, python_peak = tracemalloc.get_traced_memory()
        try:
            current_rss = rss_bytes()
        except OSError:
            current_rss = None
        samples.append(
            {
                "project": repeat,
                "python_retained_mb": (python_current - baseline_python) / MB,
                "python_peak_delta_mb": (python_peak - baseline_python) / MB,
                "rss_retained_delta_mb": (
                    (current_rss - baseline_rss) / MB
                    if current_rss is not None and baseline_rss is not None
                    else None
                ),
                "rss_peak_delta_mb": (
                    (rss_peak.peak_bytes - baseline_rss) / MB
                    if rss_peak.peak_bytes is not None and baseline_rss is not None
                    else None
                ),
            }
        )
    tracemalloc.stop()

    steady = samples[len(samples) // 2 :]
    python_retained = [float(sample["python_retained_mb"]) for sample in steady]
    rss_retained = [
        float(sample["rss_retained_delta_mb"])
        for sample in steady
        if sample["rss_retained_delta_mb"] is not None
    ]
    return {
        "baseline_rss_mb": baseline_rss / MB if baseline_rss is not None else None,
        "projects": projects,
        "steady_state_window": len(steady),
        "python_retained_slope_mb_per_project": linear_slope(python_retained),
        "rss_retained_slope_mb_per_project": linear_slope(rss_retained) if rss_retained else None,
        "python_peak_delta_mb": max(float(sample["python_peak_delta_mb"]) for sample in samples),
        "rss_peak_delta_mb": max(
            (
                float(sample["rss_peak_delta_mb"])
                for sample in samples
                if sample["rss_peak_delta_mb"] is not None
            ),
            default=None,
        ),
        "samples": samples,
    }


def _print_distribution(label: str, values: dict[str, Any] | None, unit: str) -> None:
    if values is None:
        print(f"  {label}: unavailable")
        return
    print(
        f"  {label}: mean {values['mean']:.3f}{unit}, p50 {values['p50']:.3f}{unit}, "
        f"p95 {values['p95']:.3f}{unit}, range {values['min']:.3f}-{values['max']:.3f}{unit} "
        f"(n={values['n']})"
    )


def _print_report(report: dict[str, Any]) -> None:
    if "memory" in report:
        measured = report["memory"]
        print("memory (index + select + project deletion)")
        print(f"  Python peak delta: {measured['python_peak_delta_mb']:.1f} MB")
        rss_peak = measured["rss_peak_delta_mb"]
        print(f"  RSS peak delta: {rss_peak:.1f} MB" if rss_peak is not None else "  RSS: unsupported")
        print(
            f"  steady retained slope: {measured['python_retained_slope_mb_per_project']:+.3f} "
            "MB/project Python"
        )
        if measured["rss_retained_slope_mb_per_project"] is not None:
            print(
                f"  steady retained slope: {measured['rss_retained_slope_mb_per_project']:+.3f} "
                "MB/project RSS"
            )

    if "performance" in report:
        measured = report["performance"]
        print(f"performance ({measured['provider']}/{measured['model']})")
        for temperature, group in measured["groups"].items():
            print(
                f" {temperature}: {group['succeeded']}/{group['attempted']} succeeded "
                f"({group['success_rate']:.0%})"
            )
            _print_distribution("deck latency", group["deck_latency_seconds"], "s")
            _print_distribution("all outcomes", group["outcome_latency_seconds"], "s")
            _print_distribution("successful deck cost", group["successful_deck_cost_usd"], " USD")
            _print_distribution("attempt cost", group["attempt_cost_usd"], " USD")
            print(f"  failed-attempt spend: ${group['failed_cost_usd_total']:.4f}")
            _print_distribution("model calls per attempt", group["model_calls"], "")
        if measured["pricing"] is None:
            print("  cost unavailable: pass current --input-price and --output-price")
        failures = [sample for sample in measured["samples"] if not sample["success"]]
        for sample in failures:
            print(
                f"  FAILED {sample['temperature']}/{sample['task']} repeat {sample['repeat']}: "
                f"{sample['error']}"
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="resources to attach (default: this repo)")
    parser.add_argument("--only", choices=("all", "memory", "performance"), default="all")
    parser.add_argument("--repeats", type=int, default=2, help="independent cold/warm performance repeats")
    parser.add_argument("--memory-projects", type=int, default=8, help="project lifecycles to profile")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between API-backed samples")
    parser.add_argument("--input-price", type=float, help="USD per million input tokens")
    parser.add_argument("--output-price", type=float, help="USD per million output tokens")
    parser.add_argument("--json", type=Path, help="write the complete machine-readable report")
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.memory_projects < 2 or args.delay < 0:
        parser.error("repeats must be >=1, memory-projects >=2, and delay >=0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = [path.expanduser().resolve() for path in args.paths] or [REPO_ROOT]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit(f"benchmark resources do not exist: {', '.join(missing)}")
    images = [path.name for path in paths if path.is_file() and path.suffix.lower() in IMAGE_MEDIA_TYPES]
    if images:
        raise SystemExit(
            "direct image resources use an uninstrumented indexing model call; benchmark them "
            f"separately rather than reporting incomplete cost: {', '.join(images)}"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "paths": [str(path) for path in paths],
        },
    }
    if args.only in ("all", "memory"):
        report["memory"] = memory(paths, args.memory_projects)
    if args.only in ("all", "performance"):
        report["performance"] = asyncio.run(performance(paths, args))

    _print_report(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"report: {args.json}")
    return 1 if report.get("performance", {}).get("complete") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
