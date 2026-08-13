# Benchmarks

These call the analysis core directly, never over HTTP — if a benchmark ever needs the web
server running, the layering has broken. See [CLAUDE.md](../CLAUDE.md) § Benchmarks and § Targets.

## 1. Metrics

All four CLAUDE.md targets are measured here.

| Metric | How it's calculated | Why this one |
|---|---|---|
| **Cost** | Real token counts (`client.input_tokens` / `.output_tokens`, tallied by the LLM client off the actual API response) × published per-token pricing in `PRICING`. | On BYOK it's the user's bill, on subscription it's our margin — CLAUDE.md requires it be measurable per deck either way. |
| **Latency** | Wall-clock seconds around `agent.converse()` for one chat turn, `time.perf_counter()` start to finish. | Time from request to deck is the number a user waiting on a deck actually feels. |
| **Memory** | Peak Python-level allocation (`tracemalloc`) over index + select on a throwaway project, with no model call in the loop. | Footprint must not scale with resource size — the app runs alongside the user's editor, browser and build, not on a server. |
| **Quality** | Recall of `pipeline.select()`'s output against a real, published architecture essay's own file list, on the exact repo tag that essay describes. | Selection is the product — CLAUDE.md: "Build the quality benchmark before refining anything. Tuning without it is guessing." |

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

**Quality** (`quality.py`) tests selection alone — `pipeline.select()` called directly, no agent,
no model, no API key. Ground truth is [`quality_cases/`](quality_cases/): a real open-source repo
pinned to the exact tag a real, published architecture essay was written about, and the file set
that essay names as architecturally central. A case also carries hand-authored `keywords` (and
`paths`, where relevant) standing in for what a live conversation turn would have put into
`scope.keywords`/`scope.paths` before calling `select()` for real — without them, the highest-
weighted signal in `selection/score.py`'s `WEIGHTS` table (`affinity`, 1.5) never fires, and the
benchmark silently measures a keyword-blind selection the real product never runs. A case's repo
clones on demand into `.quality-cache/` (gitignored, full history — a shallow clone would starve
Standup's own git-based signals). Overlap is recall, `|selected & covered| / |covered|`, against a
60% target from CLAUDE.md § Benchmarks;
precision is reported alongside for context, not as the target, since Standup is budget-constrained
and was never asked to match the essay's exact scope. This measures the onboarding case (a whole,
unfamiliar codebase) — the recurring case ("the right three things from my last two days") has no
ground truth yet; that's open question 6, unsolved.

**Also not in the cost number**: if a `RESOURCES` entry is an image attached directly (a document,
not a codebase — see [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §6's "one exception to
indexing never touches the model"), describing it is a real, separate model call. It's a one-time,
content-hash-cached indexing cost rather than a per-deck one, so it isn't folded into the cost/turn
figures below — the benchmark prints a note when a resource would trigger it, rather than silently
excluding it.

## 2. Running it

```
python -m benchmarks.benchmark [path]
python -m benchmarks.quality
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
- **Quality has exactly one case.** One data point isn't a distribution — a single matplotlib run
  is a real, working measurement, not yet a reliable average. Adding a case is meant to be cheap
  (one new file in `quality_cases/`, matching CLAUDE.md's "extension is addition" rule); it just
  hasn't been done more than once yet.
- **A `covered` list is one person's (or in this case, this repo's own author's) judgment about
  what the essay called central**, hand-extracted from real text, not automated — it can miss
  something the essay only implies, or include something it only mentions in passing.

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

**Quality**, measured the same day against the `matplotlib` case (repo pinned at `v1.0.1`, ground
truth from its AOSA Vol. 2 essay, `slide_budget=10`):

**(pre scope-fix) 9% recall (1/11), 10% precision — well below the 60% target.** The one hit was
`pyplot.py`; the whole Artist/Figure/Axes/Axis chain the essay treats as the architecture was
missed entirely. Inspecting what was chosen instead of just what was missed: alongside genuinely
reasonable picks (`__init__.py`, `cbook.py`, `pylab.py`, `mlab.py`, the AGG backend's `src/agg.cxx`),
the 10-slide selection also included a test-fixture SVG image
(`lib/matplotlib/tests/baseline_images/...`), a `.rst` doc index, and an example script — none of
them architecture. This run called `pipeline.select()` with an empty `scope.keywords`/`scope.paths`,
which turned out to be a defect in the benchmark itself, not (only) in selection — see below.

**(post scope-fix) 27% recall (3/11), 30% precision — still well below the 60% target, but roughly
3× the pre-fix number** once the case's `keywords` (`figure`, `artist`, `axes`, `axis`, `backend`,
`renderer`) were wired into `scope.keywords`, activating the `affinity` signal. Still missed:
`artist.py`, `axis.py`, `backend_agg.py`, `figure.py`, `image.py`, `lines.py`, `patches.py`,
`text.py`. The scope-blindness was real and worth roughly 2/3 of the original gap, but it was not
the whole gap — most of the essay's own architecture chain is still absent, and the noisy,
non-architectural picks from the pre-fix run have not been re-audited yet. That remainder is
where `selection/`'s candidate filtering and weights come in next, and it's exactly why CLAUDE.md
says tuning them before this benchmark existed was guessing — now there's a number to tune against.
