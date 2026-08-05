# Benchmarks

One file per target: `quality.py`, `cost.py`, `latency.py`, `memory.py`.

Nothing is built yet. Quality comes first — tuning selection without it is guessing — and the
budgets for cost, latency and memory get set from real measurement rather than estimated now.
See [CLAUDE.md](../CLAUDE.md) § Benchmarks and § Targets.

These call the analysis core directly, never over HTTP. If a benchmark ever needs the web
server running, the layering has broken.
