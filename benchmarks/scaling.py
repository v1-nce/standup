"""Generate deterministic source fixtures for resource-size memory comparisons."""

from __future__ import annotations

import argparse
from pathlib import Path

SIZES = {"small-25": 25, "medium-100": 100, "large-400": 400}


def generate(root: Path) -> None:
    """Write equivalent Python module graphs whose only intentional difference is file count."""
    for label, count in SIZES.items():
        fixture = root / label
        fixture.mkdir(parents=True, exist_ok=True)
        (fixture / "README.md").write_text(
            f"# Deterministic scaling fixture\n\n{count} Python modules with identical structure.\n",
            encoding="utf-8",
        )
        for index in range(count):
            dependency = (index - 1) % count
            (fixture / f"module_{index:03d}.py").write_text(
                f'"""Module {index} in the scaling fixture."""\n\n'
                f"from module_{dependency:03d} import service_{dependency:03d}\n\n\n"
                f"def service_{index:03d}(value: int) -> int:\n"
                f'    """Transform a value through fixture service {index}."""\n'
                f"    return value + {index}\n",
                encoding="utf-8",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path("benchmarks/results/scaling-fixtures"),
        help="output directory (default: benchmarks/results/scaling-fixtures)",
    )
    args = parser.parse_args()
    generate(args.root)
    for label, count in SIZES.items():
        print(f"{args.root / label}: {count} modules")


if __name__ == "__main__":
    main()
