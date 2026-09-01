"""Stable prompts for independent deck-generation benchmark samples.

Each prompt runs in its own project. `COLD_TASK` measures first-request indexing plus generation;
every entry in `TASKS` measures generation after the same project's index has been warmed.
"""

COLD_TASK = ("recap", "Give me a 5-slide deck on the most important project changes")

TASKS: dict[str, str] = {
    "recap": "Give me a 5-slide deck on the most important project changes",
    "technical-audience": (
        "Build a 3-slide deck for a technical audience explaining the indexing, selection, "
        "and presentation architecture"
    ),
    "full-history": "Make an 8-slide deck covering the whole project so far",
}
