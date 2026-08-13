# Benchmarks

These call the analysis core directly, never over HTTP — if a benchmark ever needs the web
server running, the layering has broken. See [CLAUDE.md](../CLAUDE.md) § Benchmarks and § Targets.

## 1. Metrics

Four targets are first-class in CLAUDE.md; three are measured here.

| Metric | How it's calculated | Why this one |
|---|---|---|
| **Cost** | Real token counts (`client.input_tokens` / `.output_tokens`, tallied by the LLM client off the actual API response) × published per-token pricing in `PRICING`. | On BYOK it's the user's bill, on subscription it's our margin — CLAUDE.md requires it be measurable per deck either way. |
| **Latency** | Wall-clock seconds around `agent.converse()` for one chat turn, `time.perf_counter()` start to finish. | Time from request to deck is the number a user waiting on a deck actually feels. |
| **Memory** | Peak Python-level allocation (`tracemalloc`) over index + select on a throwaway project, with no model call in the loop. | Footprint must not scale with resource size — the app runs alongside the user's editor, browser and build, not on a server. |

Cost and latency come from the same real chat turns — they're the same calls, so one turn
reports both. Each is run once per entry in [`tasks.py`](tasks.py) and averaged with
`statistics.mean`, because one prompt is one lucky or unlucky sample, not a number. All tasks
run against one project, in order, the same way a real session would: only the first pays for a
cold index (see `pipeline._merge`'s cache), the rest hit it warm. That project can hold more than
one resource — a codebase plus another codebase plus documents, the way a real one does — see
resources, below.

**Not measured**: quality. [`quality.py`](quality.py) is still an empty stub — it needs
ground-truth decks to compare selection against, which don't exist yet, and tuning
`selection/`'s constants without it is guessing.

## 2. Running it

```
python -m benchmarks.benchmark [path]
```

Resources come from [`test_set.py`](test_set.py)'s `RESOURCES` — this machine's own absolute
paths to real codebases and documents, everything one project would have attached. It's
gitignored and never committed, since the paths only mean something on the machine that wrote
them; the module docstring shows the shape. Empty, or the file missing entirely, falls back to
this repo alone, so the benchmark still runs with zero setup. A path given on the command line
overrides `RESOURCES` for a one-off run against something else.

Cost and latency need a real `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` in `.env` — whichever
`active_provider()` picks is what gets measured and priced. Memory needs neither; it never calls
a model.

## 3. Results

Measured 2026-08-13, against standup's own repo (no `.test_set.json` yet — single-resource,
same as today's default), 3 tasks from `tasks.py`:

| | | Gemini Flash-Lite | Claude Opus 5 |
|---|---|---|---|
| **Latency** | recap | **9.98s** | — |
| | technical-audience | **4.28s** | — |
| | full-history | **8.12s** | — |
| | avg | **7.46s** | not measured¹ |
| **Cost** / turn | recap | **$0.0019** | — |
| | technical-audience | **$0.0024** | — |
| | full-history | **$0.0038** | — |
| | avg | **$0.0027** | not measured¹ |
| **Memory** | peak, single run | **6.0 MB** | provider-independent² |

¹ Pricing is on record in `PRICING` ($5.00 / $25.00 per M tokens, in/out) but no key was
configured in this environment to run it — not a placeholder, genuinely unmeasured. Re-run with
`ANTHROPIC_API_KEY` set to fill this column in for real.
² Memory is a separate, model-free project; it doesn't depend on which provider is active.
