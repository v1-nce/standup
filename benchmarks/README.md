# Standup benchmarks

The benchmark package measures the analysis core directly. It has two runners because online deck
generation and deterministic selection quality have different controls and failure modes:

```console
.venv\Scripts\python.exe -m benchmarks.benchmark --help
.venv\Scripts\python.exe -m benchmarks.quality --help
```

## Measurement contract

| Metric | Unit and boundary | Reported statistics |
|---|---|---|
| Cost | Input/output tokens from every model call made during one request, multiplied by model-specific USD-per-million-token rates. | Per sample and mean/p50/p95/range, split cold/warm. Model, rates, and price source are stored with the report. |
| Latency | Wall clock from entry to `agent.converse()` until a readable deck with slides exists. | Per sample and mean/p50/p95/range, split cold/warm. |
| Memory | Python allocations (`tracemalloc`) and process RSS around index + select + project deletion. | Peak delta and least-squares retained-memory slope over the latter half of project lifecycles. |
| Quality | Path recall, candidate/slide precision, and rank-sensitive nDCG from deterministic `pipeline.select()`. | Per case, macro and micro recall, macro candidate precision, and macro nDCG, split by suite. |

A report is only comparable when its resource paths, model, pricing, scenario, and sample count are
comparable. Use `--json` to retain all of those inputs and every raw sample; console summaries are
for humans, not historical analysis.

## Cost and latency scenarios

Every sample owns a fresh project and starts without a deck. This is critical: reusing one project
would turn later “build a deck” prompts into edits or no-ops and falsely call them warm generation.

- **Cold first deck:** resources are attached, then the request clock starts. Indexing and deck
  generation are both inside the boundary.
- **Warm new deck:** resources are attached and indexed before the clock starts, but the project
  still has no deck. The measured request therefore represents amortized generation without state
  contamination.

The cold scenario uses one representative recap prompt per repeat. The warm scenario uses all
prompts in [`tasks.py`](tasks.py). Performance prompts deliberately avoid calendar-relative windows,
so a repository with no commits "this week" cannot age into an unanswerable benchmark. Attempts are
never silently dropped: failures remain in the raw
report, reduce the success rate, make the performance run incomplete, and cause a non-zero exit.
Successful deck latency/cost distributions exclude failed operations because a failure has no deck.
Outcome latency and attempt-cost distributions include every attempt, and failed-attempt spend is
reported separately, so reliability failures cannot make either efficiency number look better.

`TrackedClient` records each logical model call's type, latency, token delta, success, error, and
non-sensitive response shape (command actions and whether a reply was present).
This makes the documented one/two/four-call agent budget observable instead of inferring it from a
turn total. Provider SDK retries remain inside a logical call; wire-attempt counts are not currently
exposed by the model seam.

Default pricing is accepted only for exact known model names and carries the source/date in the
report. For any other model—or after a provider price change—pass both current rates explicitly:

```console
.venv\Scripts\python.exe -m benchmarks.benchmark --only performance --repeats 3 ^
  --delay 5 --input-price 0.10 --output-price 0.40 --json benchmarks\results\performance.json
```

Direct image resources are rejected. Their cached description uses a separate indexing client, so
including them would undercount cost. Ordinary code folders and text-bearing documents are valid.

## Memory scenario

Memory needs no API key:

```console
.venv\Scripts\python.exe -m benchmarks.benchmark --only memory --memory-projects 12 ^
  --json benchmarks\results\memory.json
```

Each iteration creates, indexes, selects, deletes, and evicts one project exactly as a completed
lifecycle should. The old harness removed temporary files but left each synthetic project in
`pipeline._INDEX_CACHE`, measuring deliberate cache retention rather than lifecycle memory. The new
profile samples both Python allocations and RSS so tree-sitter, document libraries, and other native
allocations are not invisible.

The retained slope is a leak signal, not proof that memory is independent of resource size. To test
the product's resource-scaling target, run the same command against explicit small/medium/large
resource sets and compare peak deltas. Paths are embedded in JSON reports:

```console
.venv\Scripts\python.exe -m benchmarks.benchmark C:\repo-a C:\docs\brief.pdf --only memory
```

## Quality suites

```console
.venv\Scripts\python.exe -m benchmarks.quality
.venv\Scripts\python.exe -m benchmarks.quality --suite onboarding --json benchmarks\results\quality.json
.venv\Scripts\python.exe -m benchmarks.quality --enforce-target
```

### `onboarding`

The three AOSA cases retain the original externally authored labels: real repositories, full git
history, exact tags, and files named as central by published architecture essays. Cached clones are
keyed by repository and tag and verified at the expected tag commit before every run. Hand-authored
scope keywords represent the deterministic scope that precedes selection; they are inputs, not
model-generated labels.

### `recurring-regression`

`recent-auth` creates a deterministic git repository with a recent two-file auth change beside a
high-churn dependency-lock update. It checks the mechanics of time windows, prompt steering, and
selection under noise. It is synthetic and is labeled as such in every report. Passing it does **not**
resolve the product's open question about human ground truth for “the right three things from my
last two days”; primary user-labeled decks are still required for external validity.

Quality metrics intentionally answer different questions:

- **Recall:** how much labeled evidence was surfaced. Both macro (each case equal) and micro (each
  labeled path equal) prevent one aggregation choice from hiding behavior.
- **Candidate precision:** how many selected slide candidates contain any labeled evidence. This is
  candidate-based rather than dividing by every path carried by a candidate.
- **nDCG:** whether stronger graded evidence appears earlier. Binary `covered` cases use grade 1;
  cases may supply a `relevance` map for graded labels.

The 60% recall target remains a visible product target, but normal exploratory runs report rather
than fail. `--enforce-target` is the explicit CI/release gate.

### Planned `recurring-human` suite — not implemented

The existing suites cannot establish the primary product claim. The next quality suite must be a
progressive ladder, not one expensive job: deterministic schema, provenance-reference, geometry,
and export fixtures on every change; 3–5 frozen representative recurring cases for semantic
grounding and editorial evaluation during normal iteration; and rotating held-out cases
with selective human review for milestone decisions. Expand the sample only when the result is
inconclusive or before publishing a comparative claim, and cache frozen indexes plus unchanged
baseline outputs so they are not regenerated.

Each case freezes a real project snapshot and collects labels from the presenter **before** showing
generated output: request, audience, time budget, candidate stories, must-include/must-not-include
items, and ideal order. Cases split by user and project, not by deck, to prevent one person's
recurring style leaking into both train and test.

During iteration, run the proposed selector against cached current-Standup outputs on the smoke
cases. Add a Claude Code/Codex-class baseline only for milestone comparisons, with identical source
access and a comparable token budget; send close or conflicting editorial outcomes to blind human
review rather than judging every output manually. Record four separate bands; never average a
failure in a higher band away with polish in a lower one:

1. **Validity:** readable editable `.pptx`, exact requested count, commands obeyed, no structural
   overflow or collisions. Every check is a gate.
2. **Grounding:** every material claim maps to registered evidence; unsupported output scores zero.
3. **Editorial quality:** blind human pairwise preference for audience fit, focus, useful omissions,
   order, and coherence. Randomize output order and swap positions when an LLM judge is used for
   diagnostics; it is not the release oracle.
4. **Efficiency:** first-pass acceptance, fraction of slides retained, time and edit operations to
   “I would present this,” warm/cold latency, calls, tokens, cost, and peak RSS. Efficiency compares
   only systems that passed validity and grounding.

This suite compares three explicit architecture arms: the current deterministic-selection baseline,
an AI director using tools without subagents, and the same director with one bounded specialist
wave. Record whether each specialist changed the final selection, caught unsupported evidence, or
repaired a visible problem; unused calls are quality failures, not harmless overhead. Preference
memory, semantic retrieval, visual inspection, model routing, and additional specialist roles ship
only when an ablation improves held-out user outcomes at an acceptable cost delta.

## Historical comparability

Results recorded before this harness revision are not comparable: warm prompts shared a mutated
deck, failed samples were silently skipped, memory omitted RSS and retained deleted projects in the
cache, and quality reported only macro path recall/precision. Establish a new baseline from JSON
reports produced by schema version 1; do not splice old and new numbers into one trend line.
