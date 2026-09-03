"""Deterministic proof that a correction compounds across decks.

A recurring deck starts as a perfect tie - three files with identical churn, recency, centrality,
emphasis and affinity - so the deterministic cut is alphabetical and the only thing that can move it
is the project's own history. After `keep` corrects one candidate into the deck, the next `select`
must surface that candidate without being told again, shrinking the correction distance to zero.
No model, no network, no human labels.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from standup.core import pipeline
from standup.core.models import Scope
from standup.core.projects import ProjectStore

REQUEST = "recurring deck"
SCOPE = Scope(slide_budget=1)


def _fixture(root: Path) -> Path:
    repo = root / "recurring"
    (repo / "src").mkdir(parents=True)
    for name in ("a.py", "b.py", "c.py"):
        (repo / "src" / name).write_text("def work():\n    return None\n", encoding="utf-8")
    for command in (
        ["init", "-q"],
        ["config", "user.email", "benchmark@example.com"],
        ["config", "user.name", "Standup Compounding"],
        ["add", "-A"],
        ["commit", "-qm", "first commit"],
    ):
        subprocess.run(["git", "-C", str(repo), *command], check=True, capture_output=True)
    return repo


def _order(deck) -> list[str]:
    return [entry.candidate.id for entry in [*deck.selection.chosen, *deck.selection.cut]]


def measure() -> dict[str, Any]:
    """Run the recurring scenario once and report whether the correction compounded."""
    with tempfile.TemporaryDirectory(prefix="standup-compounding-") as home:
        repo = _fixture(Path(home))
        store = ProjectStore(Path(home) / "projects")
        made = store.create("recurring")
        resource = store.attach(made.id, str(repo))
        index = asyncio.run(pipeline.indexed(store, made.id))
        preferred = f"{resource.id}/src/b.py"

        before = pipeline.select(store, made.id, index, REQUEST, SCOPE)
        pipeline.edit(store, made.id, [preferred])
        after = pipeline.select(store, made.id, index, REQUEST, SCOPE)

    def rank(deck, candidate: str) -> int:
        return _order(deck).index(candidate)

    return {
        "preferred": "src/b.py",
        "budget": SCOPE.slide_budget,
        "rank_before_correction": rank(before, preferred),
        "rank_after_correction": rank(after, preferred),
        "chosen_before_correction": preferred in {e.candidate.id for e in before.selection.chosen},
        "chosen_after_correction": preferred in {e.candidate.id for e in after.selection.chosen},
        "compounded": rank(after, preferred) < rank(before, preferred),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the machine-readable report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        **measure(),
    }
    before = (
        "chosen"
        if report["chosen_before_correction"]
        else f"rank {report['rank_before_correction']}"
    )
    after = (
        "chosen"
        if report["chosen_after_correction"]
        else f"rank {report['rank_after_correction']}"
    )
    print(
        f"correction compounds: {report['preferred']} moves from {before} to {after} "
        f"after one keep, without being asked again"
    )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"report: {args.json}")
    return 0 if report["compounded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
