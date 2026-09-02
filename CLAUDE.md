# Standup

Whatever you need to present → slide deck. Full framing is in [docs/SPECS.md](docs/SPECS.md) and [README.md](README.md); the system and agent diagrams are maintained in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — read it before non-trivial work.

The user registers resources once — a codebase **and its git history**, documents, past decks — then chats to ask for a deck. Four steps: **index** the registered resources → **gather** what the request puts in play → **select** what belongs → **present** it as slides. Selection is the product.

**One project, one deck.** A project holds one deck, one conversation, and the resources it was given.

**The orchestrator is the single owner of a request and the only model entry point.** It reads the conversation, decides which bounded job to delegate, invokes deterministic tools, validates their results, and answers — the way Claude Code edits a file. The current `select`, `keep`, and `write` commands are deterministic execution tools, not a replacement for model judgment. A future specialist may be deployed only by the orchestrator with an isolated, tailored context and explicit job/budget; it cannot call peers or mutate the deck directly. The current budget remains one call for conversation, two for an edit, four for a new deck — select, then the editorial cut (`keep`), then write, then answer. There is no command for the `.pptx` — slides are the deck, and the file is rendered when it is downloaded. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §§6 and 8.2.

**The user does not know what to present.** They have a rough idea and a deadline, twice a week. That is the whole reason the product exists, and the reason selection cannot be delegated back to them.

## What exists

Verified 2026-08-24. **Backend: 320 tests. Frontend: 40.** Both in CI.

- **Built and working** — index (tree-sitter symbols, import graph, git history, doc emphasis), gather (deterministic scope validation + candidates), selection (five signals, weights, MMR), present (groundedness validation, `.pptx`), the agent loop and its deterministic commands, the job runner, the project store and chat log, the provider seam over Anthropic and Gemini, and the HTTP API over all of it.
- **Wired end to end** — the GUI reads and writes real projects, sends a message, polls the job, and renders the deck the agent wrote. Types are generated from the backend's OpenAPI schema.
- **Context is what a project may draw on** — created from a name alone, then given **many folders and many documents** through the `+`. **A folder is named by its path; a document is handed over whole** — a page is never told where a dropped file lives, and that asymmetry is the whole design rather than something to hide. So: a path field with an `Add`, and a drop zone with an `Add file` over `<input type="file">`. Two attempts to make it one control were built and both deleted — an in-app file browser, then the machine's own dialog through `POST /pick` (`ctypes` over `GetOpenFileNameW`, with the filename box carrying a sentinel so one dialog could return a folder). Both worked and both read as vibed. **Nothing platform-specific survives**; the browser does the only part it is allowed to do. A folder is referenced where it lives; a document is copied in, whether picked or dropped. Attaching never returns 409 — indexing queues per project instead of refusing, which is what "one job per project" got wrong. Each resource is indexed and cached on its own; `index.merged` prefixes every path with its resource id, so `repo-a/src/main.py` cannot collide with `repo-b/src/main.py`, and then ranks the whole set **once**. Rank is relative: computed per resource and merged, a lone attached file would score ≈1.0 and flatten a 3000-file repository to ≈0. A document's extracted text is its only evidence, so it travels on `FileFacts.excerpt` and reaches both `evidence` and `_affinity`.
- **Not built** — diagrams, SSE, prompt caching, packaging. Briefs were a designed stage and the empty seam holding their place is now **deleted**; they return only if the quality benchmark earns them — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §6.
- **Benchmark harness built** — [benchmarks/](benchmarks/) measures all four targets with explicit scenario boundaries, raw samples, failure accounting, and JSON reports. The previous numbers are invalidated by the harness audit; establish the schema-v1 baseline before claiming a current product number.
- **Never measured** — every remaining tuning constant. The `WEIGHTS` table, `MAX_COMMITS`, and `MIN_NAME_LENGTH` are guesses standing in even though the benchmark to tune them against now exists — nobody has yet. `LAMBDA` **was** a unit bug: `ordered()` applied it to `relevance()`'s raw 0–5.1 sum instead of a normalised 0–1 value, so diversity acted on under 6% of the intended scale regardless of `LAMBDA`'s value ([docs/ISSUES.md](docs/ISSUES.md) S1). The unit fix stays — it's genuinely correct. The *value* `0.7` didn't survive contact with a real distribution: measured against all 3 cases, it dropped average recall 30%→14% (2 of 3 cases regressed, 1 unaffected), because directory proximity is a weak diversity signal and real architectures often concentrate in one directory — pushing away from it is wrong exactly when true. Retuned to `LAMBDA = 0.95` (diversity nearly off), which reproduces the pre-fix per-case numbers exactly. This is a measured value, not a guess reinstated, and it's expected to fall again once a better diversity signal replaces directory proximity — tracked under `S-next` in [docs/ISSUES.md](docs/ISSUES.md).

## Stack

Chosen 2026-08-02, grounded in [docs/RESEARCH.md](docs/RESEARCH.md). **One installable package**;
the GUI is source that compiles into it, not a second service. Rows marked **Not built** are
decisions on record, not claims about the code.

**GUI source — [ui/](ui/)**, which `npm run build` stages into `src/standup/web/`

| | |
|---|---|
| Next.js (App Router), React, TypeScript | The GUI users work in |
| **`output: "export"`** | Static export. The shipped product is one process and that process is Python, so it serves plain files — no SSR, no server components, no route handlers. Settled by the UX in [docs/UIUX.md](docs/UIUX.md); the packaging half of question 1 is still open |
| Tailwind CSS | Styling. shadcn/ui when a component earns it — copy-in, not a runtime dependency. **Not yet used** |
| Vitest + Testing Library | Unit tests. Not Jest — Vitest reuses the Vite pipeline already present |
| `openapi-typescript` | API types **generated** from the backend's OpenAPI schema. Never hand-written |
| `EventSource` (browser built-in) | Progress streaming over SSE. No WebSocket — progress is one-directional. **Not built**, and neither is the backend half |

**The package — [src/standup/](src/standup/)**, installable, and the only thing that ships

| | |
|---|---|
| Python 3.12+, FastAPI, uvicorn | Long-lived service. The pipeline runs for minutes; it cannot live in a route handler |
| Pydantic | Validates LLM output *and* auto-generates the OpenAPI schema the frontend types come from — one definition, both jobs |
| asyncio + semaphore | Bounded fan-out across modules |
| CORS, `localhost:3000` only | `next dev` is cross-origin. The shipped app is same-origin and never uses it |
| SSE | Job progress to the frontend. **Not built** — trigger is the first request that outlives a browser timeout |

**Analysis core** — a library with a thin CLI, wrapped by FastAPI. The benchmark calls the library directly, never over HTTP.

| | |
|---|---|
| `tree-sitter` + `tree-sitter-language-pack` | 100+ grammars, pre-built wheels, no build step, permissive licences only. Error-tolerant — parses broken code |
| PageRank (hand-written, ~25 lines) | Over the import graph. **NetworkX was dropped**: it pulls numpy and scipy (~100MB) to run power iteration we can write in a page, and memory is a hard target. Revisit only if a benchmark measures it slow |
| MMR (hand-written, ~15 lines) | Diversity. Relevance alone yields eight slides on one subsystem |
| `git` via subprocess | **The record of what actually happened.** Commit history, diffs, authorship, branch and merge state, commit messages, and the tree. Churn is one signal it yields, not the reason it is there |
| `pypdf` | Text out of an attached PDF. **Not PyMuPDF**: 8–12× faster and AGPL-3.0 — Standup is distributed with a paid subscription beside it, so that licence reaches the whole product. Extraction is once per document and cached, so the speed buys nothing. `pypdfium2` (permissive, faster) is the upgrade path if quality measures short, at the cost of a compiled binary per wheel |
| `openpyxl` | Cell text out of an attached `.xlsx`. Pure Python, MIT, no compiled binary — nothing read spreadsheets before this, so nothing is replaced |
| `python-docx` | Paragraph and table text out of an attached `.docx`. Same shape of choice as `openpyxl`: pure Python, MIT, first of its kind here |
| `python-pptx` | Also reads an attached `.pptx`'s text frames and tables, not only the deck it renders below — one dependency, two directions |
| `python-multipart` | FastAPI cannot accept an upload without it, and a browser cannot send a dropped file any other way |

**Model**

| | |
|---|---|
| Anthropic SDK, `claude-opus-5` | `messages.parse()` + Pydantic gives schema-bound output with SDK-level retry |
| Gemini via AI Studio REST | A **free stand-in for development**, behind the same interface. `gemini-flash-lite-latest` — the thinking models spend their whole budget before answering. Weaker at following the scope prompt than Opus; don't tune anything against it |
| Vision, both providers | An attached image has no text to extract, so `read()` sends it as an image content block and caches the reply by content hash. **The one exception to "indexing never touches the model"** — everything else in the index is derived for free; an image's evidence costs one call, made once, at attach time |
| Prompt caching | Stable repo prefix first, volatile content last (512-token minimum on Opus 5). **Not built** |
| Batch API | **Benchmarks only.** 50% cheaper, hour-scale latency — fatal for interactive use. **Not built** |

**Model access — two paths, both first-class from day one**

Standup is installed and run on the user's own machine. It cannot call a model until the user connects one, and there are exactly two ways:

| Path | What happens | Who pays |
|---|---|---|
| **Bring your own key** | The user pastes a provider key. Requests go straight to that provider. We never see the traffic and earn nothing. | User → provider |
| **Subscription** | The user signs in. Requests route through our hosted gateway, which holds the real key. | User → us; we earn the margin |

Both live behind one interface in `src/standup/core/llm/`. **Nothing outside that folder knows which path is active** — not the stages, not the pipeline, not the API. Errors from both are mapped to the same typed failures, or the abstraction leaks the first time a subscription lapses.

Subscription is the frictionless default and the revenue; BYOK is not a grudging fallback and must not rot. If a change makes one path work and the other break, it isn't done.

**Distribution** — a local install, not a service. One command to install, one command to run. The core app is free so adoption is unconstrained; the subscription is the business.

**Rendering**

| | |
|---|---|
| D2 → SVG | Single Go binary, no browser. **Not Mermaid** — `mermaid-cli` needs Chromium (~300–400MB), which breaks the memory target. D2's PNG path also spawns Playwright, so stop at SVG. **Not built** — blocked on question 1, since a Go binary is exactly what "one command" has to swallow |
| cairosvg | SVG → PNG in-process. **Not built** |
| python-pptx + a template `.pptx` | Native, editable downstream. python-pptx cannot create slide masters, so all layouts live in the template — which is also the content/layout decoupling that makes Gamma's output reliable. **The template does not exist yet**; `present/deck.py` uses python-pptx's default and takes whatever layouts come with it |

**Storage** — content-hash keyed files; JSON for the editable selection artifact. A project's index persists between decks: indexing is amortised across months of use, not repeated per deck. No database until one is needed.

**Tooling** — ruff and pytest on the package, Vitest and ESLint on the GUI, all wired into CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)). Dependencies and the `standup` entry point live in [pyproject.toml](pyproject.toml); install with `pip install -e ".[dev]"`. uv and pnpm are the intent and neither is in use: `venv` + pip, and npm, because `corepack enable` needs administrator rights on the development machine. No Docker anywhere — users must never need it, and nothing here does. Shipping is a separate problem and is unsolved — see open question 1.

### Deliberately excluded

Vector DB, embeddings, chunking, RAG — Standup does one structured extraction per module against known input, not open-ended Q&A. Dropping retrieval removes the whole layer *and* its failure modes. This is the largest single cost, latency, and memory win in the design.

**This exclusion is under pressure and has not been re-decided.** The justification above assumed a fixed job against known input. A chat interface issuing arbitrary requests over arbitrary registered resources is closer to open-ended Q&A than that sentence allows. The exclusion may well still hold — narrowing by structure, time and dependency is not semantic search — but the original reason no longer covers the product. Open question 1.

Also out: LangGraph/LangChain, Kubernetes, Postgres, Redis, Celery, and Puppeteer/Playwright. **The agent loop ships, the framework does not** — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) keeps the loop owned because its reliability, context, and cost are the product.

**Auth is in, multi-tenancy is out.** These were previously excluded together, and they are not the same thing. Signing in to the subscription needs accounts, tokens and refresh — that is real auth and it ships. Nothing else does: no per-user isolation, no roles, no sharing, no tenancy. Standup runs as one person on one machine, and the account exists to authorise a gateway, not to partition a server.

**Deferred, with a trigger:** TanStack Query (when hand-rolled fetching gets ugly), LibreOffice render-and-inspect self-check (earn it with a measurement — it is the heaviest dependency available), rustworkx (when PageRank measures slow).

### Rules

- **Don't add a dependency without naming what it replaces.** The excluded list above is load-bearing.
- **The analysis core stays independent of FastAPI and Next.js.** If the benchmark can't run without a web server, the layering is wrong.
- Frontend types are generated from the backend schema. A hand-written interface mirroring a Pydantic model is a bug.

## Code

Every implementation is modular, extensible, and complete in its stated scope. Two failure modes, equally fatal:

- **Sprawl** — the same logic in three places, files that only accumulate, boundaries that leak. Comes from adding without deleting.
- **Gold-plating** — an abstraction for one caller, config for a constant, error handling for cases that cannot occur. Comes from reading "perfect" as "more".

The rules below exist to defeat both. A change that fixes one by causing the other has failed.

### Structure

- **One home per concept.** A rule, a threshold, a prompt, a schema lives in exactly one place. Found in two → one of them is a bug, not a copy.
- **Boundaries are contracts, not conventions.** The analysis core imports nothing from FastAPI or the web layer. The frontend reaches the backend only through generated types. A cross-boundary import is a design error, not a shortcut.
- **Extension is addition.** A new importance signal, renderer, or language should be a new file plus one line in a registry. If it needs edits in five files, the seam is missing — build the seam, then add the thing.
- **Modules declare their contract.** Typed inputs, typed outputs, and one sentence saying what the module owns. If that sentence needs an "and", the module does two things.
- **Dependencies point at contracts, not at data.** A module declares the shape it needs; whatever supplies it conforms. If a component imports its prop type from the mock-data file, deleting the mock breaks the component — the arrow is backwards.
- **One file, one thing — the GUI too.** A component file holding four other components is a directory nobody made yet. Composition lives in the page; rendering lives in a component; behaviour with its own rules — a throttle, a key handler, a clamp — lives in a hook. A 200-line page passes the 300-line check and is still wrong.
- **Depth is a smell.** A file past ~300 lines, a function past ~50, a call chain past three hops. None are illegal; all mean stop and look. Usually two concepts are sharing a home.
- **A new module, moved boundary, or new call path updates the two diagrams in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) in the same change.** A stale architecture diagram is worse than no diagram.

### Comments and docstrings — minimal

Clear code needs less prose than you think, and stale prose is worse than none.

- **Docstrings only where the contract isn't obvious from the signature.** One line. A public module or a function with a non-obvious contract earns one; `def get_name(self) -> str` does not.
- **No inline comments restating the code.** `# increment counter` is noise. Comment *why*, never *what* — a non-obvious constraint, a workaround and its reason, a deliberate simplification and its ceiling.
- **No section banners, no ASCII dividers, no `Args:`/`Returns:` blocks** duplicating type hints.
- Design rationale belongs in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), not in a header comment that will drift from it.

If a comment is needed to explain what the code does, rename things until it isn't.

### Bug fixes

Every bug this session was found by hand — a pasted transcript, a manual click-through — and the
fix count (40+ file changes) grew faster than the bug count shrank. That gap has one cause: each fix
matched the one call site a transcript happened to name, not the function every sibling path also
routes through.

- **Grep every caller before touching the function.** A bug fixed at one of five call sites is a bug
  fixed 20% of the time. Find the point all callers converge on and land the fix there — not the path
  that happened to get reported.
- **The manual repro that found it becomes the check that stays.** A bug found by pasting a
  transcript and fixed without turning that transcript into a kept test has no way to announce it
  came back. This is "every non-trivial change leaves a check behind," applied specifically to
  defects, not only to new logic.
- **The same defect shape appearing twice means the abstraction is wrong, not that a third patch is
  due.** Stop, name the shared cause, and fix the seam — not the next call site.
- **Not built: a scenario suite.** Realistic multi-turn conversations run end-to-end before an
  agent/pipeline change ships — the same discipline `benchmarks/quality` already applies to
  selection, but gating on "does it break" instead of "is it good." Until it exists, every fix is
  verified against only the one conversation that broke it, which is the mechanism behind the
  circularity above.

### Completeness

- **A caveat is a defect, not a disclaimer.** "This works, except…" means it is not done. Fix it, or cut the scope until the sentence is unnecessary. Scope may be small; it may not be leaky.
- **No silent partial handling.** An unsupported case raises. Never a wrong answer, never a quiet default, never a fallback that hides the failure. In the GUI this means no unwired seam: an optional callback nothing passes is a dead control that looks alive.
- **A cast is where type-checking stops.** `as`, `# type: ignore`, `any` — each one is a claim the compiler now takes on trust, and it is exactly where the bug hides. Narrow with a real check instead; if you must assert, say why in one line.
- **Delete what you replace.** The old path goes in the same change. No dead code, no commented-out blocks, no "kept just in case" — git is the just-in-case.
- **Every non-trivial change leaves a check behind** — the smallest thing that fails if the logic breaks. Verified means executed, not reasoned about.

### Honesty

Report what was verified, not what ought to work. "Tests pass" requires having run them. If part is unfinished or unmeasured, name which part and why.

Surfacing a trade-off *before* a decision is not a caveat — Targets below requires it. A caveat is what gets attached *after* shipping something already known to be incomplete. The first is the job; the second is the thing this section forbids.

## Targets

Four, all first-class:

- **Cost** — spend per deck generated. Now has two readers: on BYOK it is the user's bill, on subscription it is our margin. Same number, and it must be measurable per deck either way.
- **Latency** — time from request to deck.
- **Memory** — footprint must not scale with resource size. This is now a hard constraint rather than a preference: Standup runs on a laptop that is also running the user's editor, browser and build.
- **Quality** — selection overlap against human-made decks. See Benchmarks.

No priority order between them is set. When a change trades one against another, surface the trade and let the user rank it — don't pick silently.

## Invariants

Break these and it's a different product.

- **Importance is inferred, not asked for.** Signals already present in the registered resources — what changed and when, what depends on what, what sits on real paths, what the project's own docs emphasise, what is genuine decision versus routine — rank a shortlist, and the director makes the final cut from it. The user's request *steers* the search: it sets scope, window and audience. It does not answer the question, because the user does not know the answer. A model asked directly which parts matter answers "all of them"; that's the failure mode the whole product exists to avoid.
- **Git is the record; the prompt is the memory.** The user says what they *think* they did after two blurred days. Git says what they *actually* did, with timestamps, authorship and completion state. Where the two disagree, git wins and the prompt is treated as a search hint. Reconciling the two is the job.
- **Judgment ranks and cuts; language comes after.** Narrative and phrasing are applied to decisions already made, never the other way round.
- **Selection is visible and editable.** The user sees what was chosen and why, and can change it before the deck is built.
- **Correcting a choice is cheap, and the correction is obeyed.** A wrong selection costs a small edit, not a full regeneration. Remove an item and it's gone; reorder and that order holds; only the affected slides re-render. A correction you have to argue with is not cheap.
- **The agent chooses the command; the command runs literally.** Saying "drop the weights one" is a correction, not a suggestion, because the model's only power is to *name* an operation — `keep` reorders exactly as told, `write` touches only the slides it names, and everything the agent writes is checked against the index before it is kept. The model never re-ranks the numbers: scores and signals are withheld from its prompt, so its `keep` cut is a judgment on the evidence shown, not a re-scoring. This is what lets chat be the editing surface without the edit becoming a negotiation.
- **The user's resources stay on the user's machine.** Registering a codebase points at a path; it does not upload it. Indexing, artifacts, decks and history are all local. The only thing that ever leaves is the content of a bounded model call, and the user chose where that goes when they picked a path. Anything that quietly widens what leaves is a breach of the product, not an optimisation.

## Benchmarks

[benchmarks/](benchmarks/) is the home for measurement — all four targets have explicit metric boundaries. Run
`python -m benchmarks.quality` and `python -m benchmarks.benchmark`; the measurement contract and controls
and comparability rules live in [benchmarks/README.md](benchmarks/README.md); this section states
only what those numbers mean for the project.

**Quality** reports macro/micro path recall, candidate precision, and rank-sensitive nDCG. The
`onboarding` suite uses published architecture essays on exact repository tags. Its 60% target,
below which selection logic needs work rather than polish, remains in force. The three AOSA cases
remain externally grounded. A synthetic `recurring-regression` case checks recent-work mechanics;
it does not replace human recurring-deck labels.

**Cost and latency** isolate cold and warm new-deck scenarios, model calls, and failed attempts. See
benchmarks/README.md for the full contract. **Memory** measures Python allocations and RSS across

complete project lifecycles. Prior harness results are not comparable. Human ground truth for "the
right three things to say about my last two days" remains unsolved — open question 6.

**Tuning against the benchmark, not before it, has now actually happened once** (close-out plan, Phase 4, 2026-08-14) — every `selection/` change measured before/after against all 3 cases, one signal at a time, nothing forced through on a guess:

- `LAMBDA`'s scale-unit fix (S1) was the counter-example that started this discipline: shipped as a correctness fix, only measured afterward, and it dropped the one quality case that existed then from 36% to 9%. Adding two more cases and re-measuring both ways confirmed the regression was real, not a fluke of n=1: 30%→14% average across all three. The scale fix stayed (genuinely correct); `LAMBDA` retuned 0.7→0.95, reproducing the pre-fix numbers exactly.
- `S10` (rename parsing) and `S11` (case-consistent emphasis matching) are real correctness fixes, parameter-free, and measured **benchmark-neutral** — 30%→30% avg both times, not one case moved.
- `S4` (log1p on churn) and `S5` (word-boundary affinity matching) are also parameter-free and measured as **real improvements**: 30%→34% average recall, nothing regressed. `S5` — the highest-weighted signal — did almost all of that work alone (twisted alone: 25%→38%).
- `S6` (recency decay) was tried at two half-lives and **parked**: 30 days regressed the average (30%→28%); 180 days landed back at 30% but with a different, not better, per-case split. Picking a half-life from 3 cases would have repeated the exact S1 mistake, so it was reverted rather than forced through. Full accounting per signal in [docs/ISSUES.md](docs/ISSUES.md).

## Working agreements

- Any change touching selection → re-measure against the benchmark and report the delta. A quality gain that doubles cost is a decision to surface, not a win to claim.
- Prefer inference from the codebase over asking a model, wherever the answer is derivable.
- The evidence in SPECS establishes that comprehension is expensive and onboarding is slow. It does **not** establish that a deck is the remedy, and it does **not** cover the recurring-presentation framing at all — nobody has measured how often engineers present or what preparing costs them. Both gaps close with primary research, not more desk research. Don't treat either as settled.

## Open questions

**Nothing below is decided.** Don't pick one silently to unblock yourself — ask.

| # | Question | What it changes |
|---|---|---|
| 1 | **How does this ship as one command?** | A Python runtime, a Node build and a `d2` binary do not install with one command today, even though the package itself now does. **The frontend half is settled**: [docs/UIUX.md](docs/UIUX.md) says `standup` opens a browser from one process, so Next.js is a static export and always will be. The packaging half is untouched — how the Python runtime, the built assets and `d2` arrive on a stranger's machine from one line. |
| 2 | **How long until a new user's first deck?** | Every deck after the first is cheap because the project is indexed. The first is not, and it lands exactly where someone decides whether to keep the tool — Gamma manages nothing-to-deck in under a minute. Indexing the recent window before the full history would help; nothing is measured. |
| 3 | Is BYOK single-provider or multi-provider? | Whether `src/standup/core/llm/` normalises across wire formats or only ever speaks Anthropic. Presenton supports four; supporting one is far cheaper and may be enough. |
| 4 | What does the gateway retain, and what do we tell users? | The subscription path routes their code through us. The answer is a product promise before it is a schema. |
| 5 | Does gathering need semantic retrieval, or is structural narrowing enough? | Whether embeddings and a retrieval layer come back in — see Deliberately excluded |
| 6 | What is ground truth for a recurring update? | Whether selection quality is measurable at all in the primary use case |
| 7 | Which resources beyond a codebase come first, and what does each cost to integrate? | Scope of the index layer, and whether third-party auth enters the system |
| 8 | Is requested slide count a hard limit or a target? | How selection behaves when the evidence doesn't divide cleanly |
| 9 | Does code itself appear on slides, or only descriptions? | What a slide can contain |
| 10 | How wrong can selection be before output stops being useful? | Sets the bar the benchmark must clear |
| 11 | One audience served well, or several adequately? | Scope of the presentation step |
| 12 | Does a single overlap metric suffice, or does the benchmark need PPTEval's Content / Design / Coherence split? | Whether a deck can pass while being incoherent |
| 13 | Is relevance enough, or is diversity a first-class signal? | Whether MMR sits in the ranking or is bolted on after |

**This is the canonical list.** [docs/SPECS.md](docs/SPECS.md) carries the product-facing subset and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) the ones that change the system's shape; both point here. Questions 1–4 came from the distribution decision on 2026-08-03, 5–7 from the product reframing the same day, 12 and 13 from [docs/RESEARCH.md](docs/RESEARCH.md). The stack question closed on 2026-08-02; question 1 partially reopens it.
