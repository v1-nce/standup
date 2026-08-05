"""How much each signal counts. One table, and nothing else decides relevance."""

from selection.signals import SIGNALS

WEIGHTS = {
    "churn": 1.0,
    "recency": 1.0,
    "centrality": 1.0,
    "emphasis": 0.6,
    # The request steers the search, so it outweighs any single derived signal - but not their sum,
    # or naming one thing would bury everything the user forgot to mention.
    "affinity": 1.5,
}

_unweighted = set(SIGNALS) - set(WEIGHTS)
if _unweighted:
    raise RuntimeError(f"Signals with no weight, so they would count for nothing: {_unweighted}")


def relevance(signals: dict[str, float]) -> float:
    return sum(WEIGHTS[name] * value for name, value in signals.items())
