"""Deterministic selection-quality benchmark with ranked, candidate-level reporting.

The onboarding suite uses real repositories pinned to the tags described by published AOSA essays.
The recurring suite is a synthetic regression fixture with known commits and noise; it verifies the
mechanics of a recent-work request but is explicitly not a substitute for human recurring-deck
labels. No model or API key is used.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.metrics import quality_metrics
from standup.core import pipeline
from standup.core.models import Scope
from standup.core.projects import ProjectStore

CASES_DIR = Path(__file__).parent / "quality_cases"
CACHE_DIR = Path(__file__).parent / ".quality-cache"
TARGET_RECALL = 0.60


def _load_cases() -> list[dict[str, Any]]:
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(CASES_DIR.glob("*.json"))]
    names = [case.get("name") for case in cases]
    if len(set(names)) != len(names):
        raise ValueError("quality case names must be unique")
    for case in cases:
        missing = {"name", "suite", "request", "slide_budget"} - case.keys()
        if missing:
            raise ValueError(f"{case.get('name', '<unnamed>')} is missing {sorted(missing)}")
        if not case.get("covered") and not case.get("relevance"):
            raise ValueError(f"{case['name']} needs covered paths or graded relevance")
    return cases


def _run_git(path: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed.stdout.strip()


def _trust_cached_clone(path: Path) -> None:
    """Trust only this benchmark process's generated clone, never global git configuration."""
    offset = int(os.environ.get("GIT_CONFIG_COUNT", "0") or "0")
    os.environ["GIT_CONFIG_COUNT"] = str(offset + 1)
    os.environ[f"GIT_CONFIG_KEY_{offset}"] = "safe.directory"
    os.environ[f"GIT_CONFIG_VALUE_{offset}"] = path.resolve().as_posix()


def _cloned(repo: str, tag: str, name: str) -> Path:
    key = hashlib.sha256(f"{repo}\0{tag}".encode()).hexdigest()[:10]
    keyed = CACHE_DIR / f"{name}-{key}"
    legacy = CACHE_DIR / name
    dest = keyed if keyed.exists() or not legacy.exists() else legacy
    if not dest.exists():
        CACHE_DIR.mkdir(exist_ok=True)
        subprocess.run(
            ["git", "clone", "--branch", tag, "--no-single-branch", repo, str(dest)],
            check=True,
        )
    _trust_cached_clone(dest)
    head = _run_git(dest, "rev-parse", "HEAD")
    expected = _run_git(dest, "rev-parse", f"{tag}^{{commit}}")
    if head != expected:
        raise RuntimeError(
            f"quality cache {dest} is not pinned to {tag}: expected {expected}, found {head}"
        )
    return dest


def _write(repo: Path, relative: str, content: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str, at: str) -> None:
    _run_git(repo, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_DATE=at, GIT_COMMITTER_DATE=at)
    _run_git(repo, "commit", "-qm", message, env=env)


def _recurring_fixture(root: Path) -> Path:
    """A recent auth feature beside a high-churn dependency-lock update."""
    repo = root / "recurring"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "benchmark@example.com")
    _run_git(repo, "config", "user.name", "Standup Benchmark")
    _write(repo, "src/app.py", "def main():\n    return 'ready'\n")
    _write(repo, "src/auth/session.py", "def open_session():\n    return True\n")
    _write(repo, "src/auth/token.py", "def issue_token():\n    return 'token'\n")
    _write(repo, "uv.lock", "base\n")
    _commit(repo, "Initial application", "2026-08-01T09:00:00+00:00")

    _write(
        repo,
        "src/auth/session.py",
        "from .token import rotate_token\n\ndef refresh_session():\n    return rotate_token()\n",
    )
    _write(repo, "src/auth/token.py", "def rotate_token():\n    return 'rotated'\n")
    _commit(repo, "Add refresh-token session flow", "2026-08-13T09:00:00+00:00")

    _write(repo, "uv.lock", "\n".join(f"dependency-{number}" for number in range(2_000)))
    _commit(repo, "Refresh dependency lock", "2026-08-14T09:00:00+00:00")
    return repo


@contextmanager
def _repo(case: dict[str, Any]):
    fixture = case.get("fixture")
    if fixture:
        if fixture != "recurring":
            raise ValueError(f"unknown quality fixture {fixture!r}")
        with tempfile.TemporaryDirectory(prefix="standup-quality-fixture-") as home:
            yield _recurring_fixture(Path(home))
        return
    yield _cloned(case["repo"], case["tag"], case["name"])


async def _selected(repo_path: Path, case: dict[str, Any]) -> list[list[str]]:
    with tempfile.TemporaryDirectory(prefix="standup-quality-") as home:
        store = ProjectStore(Path(home))
        made = store.create("quality")
        resource = store.attach_path(made.id, str(repo_path))
        try:
            index = await pipeline.indexed(store, made.id)
            if index is None:
                raise RuntimeError("quality case produced no index")
            scope_data = {
                "slide_budget": case["slide_budget"],
                "keywords": case.get("keywords", []),
                "paths": case.get("paths", []),
                **case.get("scope", {}),
            }
            deck = pipeline.select(
                store,
                made.id,
                index,
                case["request"],
                Scope.model_validate(scope_data),
            )
            prefix = f"{resource.id}/"
            return [
                [path.removeprefix(prefix) for path in entry.candidate.paths if path.startswith(prefix)]
                for entry in deck.selection.chosen
            ]
        finally:
            try:
                store.delete(made.id)
            finally:
                pipeline.evict(made.id)


def _relevance(case: dict[str, Any]) -> dict[str, float]:
    if "relevance" in case:
        return {path: float(grade) for path, grade in case["relevance"].items()}
    return {path: 1.0 for path in case["covered"]}


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    with _repo(case) as repo_path:
        selected = asyncio.run(_selected(repo_path, case))
    metrics = quality_metrics(selected, _relevance(case))
    return {
        "name": case["name"],
        "suite": case["suite"],
        "source": case.get("talk", "synthetic regression fixture"),
        "synthetic": bool(case.get("fixture")),
        "selected": selected,
        **metrics,
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    hits = sum(int(case["hits"]) for case in cases)
    relevant = sum(int(case["relevant"]) for case in cases)
    return {
        "cases": len(cases),
        "macro_recall": statistics.mean(float(case["recall"]) for case in cases),
        "micro_recall": hits / relevant if relevant else 0.0,
        "macro_candidate_precision": statistics.mean(
            float(case["candidate_precision"]) for case in cases
        ),
        "macro_ndcg": statistics.mean(float(case["ndcg"]) for case in cases),
        "target_recall": TARGET_RECALL,
    }


def _print(report: dict[str, Any]) -> None:
    for suite, aggregate in report["suites"].items():
        print(f"{suite} ({aggregate['cases']} case(s))")
        for case in [case for case in report["cases"] if case["suite"] == suite]:
            label = " [synthetic regression]" if case["synthetic"] else ""
            print(
                f"  {case['name']:12s} recall {case['recall']:5.0%} "
                f"({case['hits']}/{case['relevant']}), candidate precision "
                f"{case['candidate_precision']:5.0%}, nDCG {case['ndcg']:5.0%}{label}"
            )
            if case["missed"]:
                print(f"    missed: {', '.join(case['missed'])}")
        print(
            f"  macro recall {aggregate['macro_recall']:.0%}; "
            f"micro recall {aggregate['micro_recall']:.0%}; "
            f"candidate precision {aggregate['macro_candidate_precision']:.0%}; "
            f"nDCG {aggregate['macro_ndcg']:.0%}; target {aggregate['target_recall']:.0%}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", help="run only this suite (repeatable)")
    parser.add_argument("--json", type=Path, help="write the complete machine-readable report")
    parser.add_argument(
        "--enforce-target",
        action="store_true",
        help="exit non-zero when any suite's macro recall is below target",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = _load_cases()
    if args.suite:
        wanted = set(args.suite)
        cases = [case for case in cases if case["suite"] in wanted]
    if not cases:
        raise SystemExit("no matching quality cases")

    results = [run_case(case) for case in cases]
    suites = {
        suite: _aggregate([case for case in results if case["suite"] == suite])
        for suite in sorted({case["suite"] for case in results})
    }
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "cases": results,
        "suites": suites,
    }
    _print(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"report: {args.json}")
    below = any(suite["macro_recall"] < suite["target_recall"] for suite in suites.values())
    return 1 if args.enforce_target and below else 0


if __name__ == "__main__":
    raise SystemExit(main())
