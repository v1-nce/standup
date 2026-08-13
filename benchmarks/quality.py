"""Selection quality: does Standup pick what a human architecture writeup says matters?

Ground truth lives in quality_cases/*.json — a real open-source repo pinned to the exact tag a
real, published architecture essay was written about, and the file set that essay names as
architecturally central (see each case's "talk" field). A case's repo is cloned on demand into
.quality-cache/ (gitignored) at that pinned tag, with full history — a shallow clone would starve
Standup's own git-based signals (churn, recency), understating exactly what this measures.

This tests selection alone, not the agent or the model: pipeline.select() is called directly, the
same deterministic entrypoint gather/select already exposes. No LLM call, no API key needed —
CLAUDE.md: "Judgment ranks and cuts; language comes after." Quality is a ranking question here,
not a wording one.

A case's "keywords" (and "paths", where relevant) stand in for what a live conversation turn would
have extracted into scope.keywords/scope.paths before calling select() for real — hand-authored
here instead of inferred, so the affinity signal (selection/signals.py, the highest-weighted signal
there is) gets exercised without spending a model call to get it. A case with no keywords tests
decontextualized ranking only, understating what a real request-scoped turn would surface.

Overlap is recall: |selected & covered| / |covered| — did Standup surface what the essay covered,
not whether it covered ONLY that (Standup is budget-constrained and was never asked to match the
essay's scope). Precision is reported alongside for context, not as the target. Initial target:
60% recall (CLAUDE.md § Benchmarks) — below that, selection logic needs work, not polish.

This measures the onboarding case (a whole, unfamiliar codebase), not the recurring one ("the
right three things from my last two days") — ground truth for that is open question 6, unsolved.

Run:  python -m benchmarks.quality
"""

import asyncio
import json
import os
import statistics
import subprocess
import tempfile
from pathlib import Path

from standup.core import pipeline
from standup.core.models import Scope
from standup.core.projects import ProjectStore

CASES_DIR = Path(__file__).parent / "quality_cases"
CACHE_DIR = Path(__file__).parent / ".quality-cache"
TARGET_RECALL = 0.60


def _load_cases() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.glob("*.json"))]


def _cloned(repo: str, tag: str, name: str) -> Path:
    dest = CACHE_DIR / name
    if not dest.exists():
        CACHE_DIR.mkdir(exist_ok=True)
        subprocess.run(["git", "clone", "--branch", tag, repo, str(dest)], check=True)
    _trust_cached_clone(dest)
    return dest


def _trust_cached_clone(path: Path) -> None:
    """This benchmark owns its cache, even when a sandbox user runs git against it later."""
    resolved = path.resolve().as_posix()
    values = [
        os.environ.get(f"GIT_CONFIG_VALUE_{i}")
        for i in range(int(os.environ.get("GIT_CONFIG_COUNT", "0") or "0"))
    ]
    if resolved in values:
        return
    offset = len(values)
    os.environ["GIT_CONFIG_COUNT"] = str(offset + 1)
    os.environ[f"GIT_CONFIG_KEY_{offset}"] = "safe.directory"
    os.environ[f"GIT_CONFIG_VALUE_{offset}"] = resolved


async def _selected(
    repo_path: Path, request: str, budget: int, keywords: list[str], paths: list[str]
) -> set[str]:
    with tempfile.TemporaryDirectory(prefix="standup-quality-") as home:
        store = ProjectStore(Path(home))
        made = store.create("quality")
        resource = store.attach_path(made.id, str(repo_path))
        index = await pipeline.indexed(store, made.id)
        scope = Scope(slide_budget=budget, keywords=keywords, paths=paths)
        deck = pipeline.select(store, made.id, index, request, scope)

    prefix = f"{resource.id}/"
    return {
        path.removeprefix(prefix)
        for entry in deck.selection.chosen
        for path in entry.candidate.paths
        if path.startswith(prefix)
    }


def run_case(case: dict) -> tuple[float, float]:
    repo_path = _cloned(case["repo"], case["tag"], case["name"])
    selected = asyncio.run(
        _selected(
            repo_path,
            case["request"],
            case["slide_budget"],
            case.get("keywords", []),
            case.get("paths", []),
        )
    )
    covered = set(case["covered"])

    hit = selected & covered
    recall = len(hit) / len(covered) if covered else 0.0
    precision = len(hit) / len(selected) if selected else 0.0

    print(
        f"  {case['name']:12s} recall {recall:5.0%} ({len(hit)}/{len(covered)})  "
        f"precision {precision:5.0%} ({len(hit)}/{len(selected)})"
    )
    missed = covered - selected
    if missed:
        print(f"    missed: {', '.join(sorted(missed))}")
    extra = selected - covered
    if extra:
        print(f"    extra: {', '.join(sorted(extra))}")
    return recall, precision


def main() -> None:
    cases = _load_cases()
    if not cases:
        print(f"no cases in {CASES_DIR} — nothing to measure")
        return

    recalls, precisions = zip(*(run_case(c) for c in cases))
    avg_recall = statistics.mean(recalls)
    print(f"\nrecall: {avg_recall:.0%} avg over {len(cases)} case(s), target {TARGET_RECALL:.0%}")
    print(f"precision: {statistics.mean(precisions):.0%} avg")
    if avg_recall < TARGET_RECALL:
        print("below target — selection logic needs work, not polish (CLAUDE.md § Benchmarks)")


if __name__ == "__main__":
    main()
