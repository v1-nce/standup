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
reports both, run against one project on one long-lived client (matching production's, not a
fresh one per turn). The **first turn ever made is reported alone, labeled cold** — it pays for
indexing this project for the first time, and "how long until a new user's first deck" (CLAUDE.md
open question 2) is a different number from steady state. Every task in [`tasks.py`](tasks.py)
then runs `REPEATS` times warm, interleaved rather than back-to-back, and reports mean, stddev and
range instead of one lucky or unlucky sample — one prompt was never a number. A warm sample that
fails (a rate limit, a transient timeout) is logged and skipped rather than crashing the run; the
printed `n=` says how many survived. That project can hold more than one resource — a codebase
plus another codebase plus documents, the way a real one does — see resources, below.

Memory runs a **sequence of `SESSION_PROJECTS` throwaway projects in one process**, sampling
retained (not peak) allocation after each, to check whether anything in `pipeline.py`'s
process-global caches (`_INDEX_CACHE`, capped at 16 entries) holds on longer than it should.
`SESSION_PROJECTS` is set above that cap on purpose: the cache filling up looks like growth too,
so the run has to go past 16 to tell "expected, then flat" apart from "still climbing."

**Not measured**: quality. It needs ground-truth decks to compare selection against, which don't
exist yet — there's nothing to build `quality.py` against, so tuning `selection/`'s constants
without it is guessing.

**Also not in the cost number**: if a `RESOURCES` entry is an image attached directly (a document,
not a codebase — see [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §6's "one exception to
indexing never touches the model"), describing it is a real, separate model call. It's a one-time,
content-hash-cached indexing cost rather than a per-deck one, so it isn't folded into the cost/turn
figures below — the benchmark prints a note when a resource would trigger it, rather than silently
excluding it.

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
`active_provider()` picks is what gets measured and priced. Memory needs neither and runs first,
so it always reports even with no key configured.

## 3. Honest caveats (please read)

- **Your numbers will vary.** API load, exact prompt phrasing, network conditions, which provider
  is active — run it yourself rather than trusting a number measured on a different machine, on a
  different day. That's the whole reason `REPEATS` exists instead of one sample per task.
- **A free-tier key rate-limits under `REPEATS`.** A "new deck" task can cost up to 3 real calls
  (CLAUDE.md's own call-budget table), so `REPEATS=2` (7 turns, up to ~21 calls) can still trip a
  free Gemini key's request-per-minute cap, especially back-to-back with other runs. The benchmark
  degrades — it logs the failure and reports a smaller `n` — rather than losing the whole run; a
  paid key or a quieter window gets you the full sample.
- **Cost excludes image-description spend** (see above) and only counts the provider currently
  active — it does not compare providers against each other the way `bench_example/cost.py` does,
  because standup has one active provider per run, not several tools to line up side by side.
  `PRICING` is a hand-maintained table; a model change that isn't priced there prints "no pricing
  on record" rather than a wrong number.
- **Memory's session check is a canary, not a leak-slope regression test.** Unlike
  `bench_example/memory_session.py`, there's no known bug being chased here, so there's no fitted
  slope or pass/fail threshold — just the raw retained-MB series. Read it yourself: rise-then-flat
  around the cache cap is healthy, still climbing past it is worth investigating.

## 4. Results

Measured 2026-08-13, against standup's own repo (no `.test_set.json` yet — single-resource, same
as today's default), 3 tasks from `tasks.py`, `REPEATS=2`, Gemini Flash-Lite (the only key
configured in this environment). Run partway into a free-tier rate limit from repeated testing
that same session — 2 of 6 warm samples were lost to a 429, which is exactly the degraded-run case
above, kept here rather than replaced with a cleaner-looking cherry-picked run:

| Task | Cold (first deck) | Warm mean | Warm n | Cost (warm avg) |
|---|---|---|---|---|
| recap | 8.79s / $0.0028 | 3.29s +/- 0.49s | 2 | $0.0021 |
| technical-audience | — | 3.46s +/- 0.00s | 1 | $0.0024 |
| full-history | — | 12.18s +/- 0.00s | 1 | $0.0050 |

Latency overall: **5.56s avg, 3.84s sd, 2.80–12.18s range** over 4 surviving warm turns. Cost
overall: **$0.0029 avg** over the same 4. Memory: **6.3 MB peak** (cold build); session growth
**+20.9 MB over 20 projects**, climbing to 22.4 MB by project 16 (the index cache filling) and
dead flat for projects 17–20 (the cache cap holding) — no leak.

Claude Opus 5 is unmeasured here — `PRICING` has it on record ($5.00 / $25.00 per M tokens) but no
`ANTHROPIC_API_KEY` was configured in this environment. Re-run with one set to fill it in for real.
