"""The requests benchmark.py measures cost and latency against — a few varied enough that one
number isn't just one lucky prompt. Run in order against one project, so only the first pays for
a cold index; the rest are the ordinary case afterward."""

try:
    from benchmarks.test_set import RESOURCES
except ImportError:
    RESOURCES: list[str] = []  # no local test_set.py — benchmark.py falls back to standup's own repo

TASKS: dict[str, str] = {
    "recap": "Give me a 5-slide deck on the recent work",
    "technical-audience": "Build a 3-slide deck for a technical audience on what changed this week",
    "full-history": "Make an 8-slide deck covering the whole project so far",
}
