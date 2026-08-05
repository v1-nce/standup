# Standup

Whatever you need to present → slide deck. Full framing in [docs/SPECS.md](docs/SPECS.md) and [README.md](README.md); system shape in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — read before non-trivial work.

The user registers resources once — a codebase **and its git history**, documents, past decks — then chats to ask for a deck. Four steps: **index** the registered resources → **gather** what the request puts in play → **select** what belongs → **present** it as slides. Selection is the product.

Two model calls in the steady state — one to read the request, one to plan the slides. Everything between them is deterministic. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §6 for the call budget; it is the number that decides whether this is usable twice a week.

**The user does not know what to present.** They have a rough idea and a deadline, twice a week. That is the whole reason the product exists, and the reason selection cannot be delegated back to them.

## Stack

Chosen 2026-08-02, grounded in [docs/RESEARCH.md](docs/RESEARCH.md). Two services.

**Frontend — [frontend/](frontend/)**

| | |
|---|---|
| Next.js (App Router), React, TypeScript | The GUI users work in |
| Tailwind CSS, shadcn/ui (Radix UI) | Components; shadcn is copy-in, not a runtime dependency |
| `EventSource` (browser built-in) | Progress streaming over SSE. No WebSocket — progress is one-directional |
| `openapi-typescript` | API types **generated** from the backend's OpenAPI schema. Never hand-written |

**Backend — [backend/](backend/)**

| | |
|---|---|
| Python 3.12+, FastAPI, uvicorn | Long-lived service. The pipeline runs for minutes; it cannot live in a route handler |
| Pydantic | Validates LLM output *and* auto-generates the OpenAPI schema the frontend types come from — one definition, both jobs |
| asyncio + semaphore | Bounded fan-out across modules |
| SSE | Job progress to the frontend |

**Analysis core** — a library with a thin CLI, wrapped by FastAPI. The benchmark calls the library directly, never over HTTP.

| | |
|---|---|
| `tree-sitter` + `tree-sitter-language-pack` | 100+ grammars, pre-built wheels, no build step, permissive licences only. Error-tolerant — parses broken code |
| NetworkX | PageRank over the symbol graph. Swap to `rustworkx` only if a benchmark demands it |
| MMR (hand-written, ~15 lines) | Diversity. Relevance alone yields eight slides on one subsystem |
| `git` via subprocess | **The record of what actually happened.** Commit history, diffs, authorship, branch and merge state, commit messages, and the tree. Churn is one signal it yields, not the reason it is there |

**Model**

| | |
|---|---|
| Anthropic SDK, `claude-opus-5` | `messages.parse()` + Pydantic gives schema-bound output with SDK-level retry |
| Prompt caching | Stable repo prefix first, volatile content last (512-token minimum on Opus 5) |
| Batch API | **Benchmarks only.** 50% cheaper, hour-scale latency — fatal for interactive use |

**Model access — two paths, both first-class from day one**

Standup is installed and run on the user's own machine. It cannot call a model until the user connects one, and there are exactly two ways:

| Path | What happens | Who pays |
|---|---|---|
| **Bring your own key** | The user pastes a provider key. Requests go straight to that provider. We never see the traffic and earn nothing. | User → provider |
| **Subscription** | The user signs in. Requests route through our hosted gateway, which holds the real key. | User → us; we earn the margin |

Both live behind one interface in `src/llm/`. **Nothing outside that folder knows which path is active** — not the stages, not the pipeline, not the API. Errors from both are mapped to the same typed failures, or the abstraction leaks the first time a subscription lapses.

Subscription is the frictionless default and the revenue; BYOK is not a grudging fallback and must not rot. If a change makes one path work and the other break, it isn't done.

**Distribution** — a local install, not a service. One command to install, one command to run. The core app is free so adoption is unconstrained; the subscription is the business.

**Rendering**

| | |
|---|---|
| D2 → SVG | Single Go binary, no browser. **Not Mermaid** — `mermaid-cli` needs Chromium (~300–400MB), which breaks the memory target. D2's PNG path also spawns Playwright, so stop at SVG |
| cairosvg | SVG → PNG in-process |
| python-pptx + a template `.pptx` | Native, editable downstream. python-pptx cannot create slide masters, so all layouts live in the template — which is also the content/layout decoupling that makes Gamma's output reliable |

**Storage** — content-hash keyed files; JSON for the editable selection artifact. A project's index persists between decks: indexing is amortised across months of use, not repeated per deck. No database until one is needed.

**Tooling** — uv, pnpm, ruff, pytest. Docker Compose is a **development** convenience only; users must never need Docker to run Standup. Shipping is a separate problem and is unsolved — see open question 1.

### Deliberately excluded

Vector DB, embeddings, chunking, RAG — Standup does one structured extraction per module against known input, not open-ended Q&A. Dropping retrieval removes the whole layer *and* its failure modes. This is the largest single cost, latency, and memory win in the design.

**This exclusion is under pressure and has not been re-decided.** The justification above assumed a fixed job against known input. A chat interface issuing arbitrary requests over arbitrary registered resources is closer to open-ended Q&A than that sentence allows. The exclusion may well still hold — narrowing by structure, time and dependency is not semantic search — but the original reason no longer covers the product. Open question 1.

Also out: LangGraph/LangChain (no agent loop — parallel one-shot calls), Kubernetes, Postgres, Redis, Celery, Mermaid, Puppeteer/Playwright.

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
- **Depth is a smell.** A file past ~300 lines, a function past ~50, a call chain past three hops. None are illegal; all mean stop and look. Usually two concepts are sharing a home.

### Comments and docstrings — minimal

Clear code needs less prose than you think, and stale prose is worse than none.

- **Docstrings only where the contract isn't obvious from the signature.** One line. A public module or a function with a non-obvious contract earns one; `def get_name(self) -> str` does not.
- **No inline comments restating the code.** `# increment counter` is noise. Comment *why*, never *what* — a non-obvious constraint, a workaround and its reason, a deliberate simplification and its ceiling.
- **No section banners, no ASCII dividers, no `Args:`/`Returns:` blocks** duplicating type hints.
- Design rationale belongs in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), not in a header comment that will drift from it.

If a comment is needed to explain what the code does, rename things until it isn't.

### Completeness

- **A caveat is a defect, not a disclaimer.** "This works, except…" means it is not done. Fix it, or cut the scope until the sentence is unnecessary. Scope may be small; it may not be leaky.
- **No silent partial handling.** An unsupported case raises. Never a wrong answer, never a quiet default, never a fallback that hides the failure.
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

- **Importance is inferred, not asked for.** Signals already present in the registered resources — what changed and when, what depends on what, what sits on real paths, what the project's own docs emphasise, what is genuine decision versus routine — decide what matters. The user's request *steers* the search: it sets scope, window and audience. It does not answer the question, because the user does not know the answer. A model asked directly which parts matter answers "all of them"; that's the failure mode the whole product exists to avoid.
- **Git is the record; the prompt is the memory.** The user says what they *think* they did after two blurred days. Git says what they *actually* did, with timestamps, authorship and completion state. Where the two disagree, git wins and the prompt is treated as a search hint. Reconciling the two is the job.
- **Judgment ranks and cuts; language comes after.** Narrative and phrasing are applied to decisions already made, never the other way round.
- **Selection is visible and editable.** The user sees what was chosen and why, and can change it before the deck is built.
- **Correcting a choice is cheap, and the correction is obeyed.** A wrong selection costs a small edit, not a full regeneration — and that edit is applied literally. No model re-interprets it, nothing gets quietly "improved" back. Remove an item and it's gone; reorder and that order holds; only the affected slides re-render. A correction you have to argue with is not cheap.
- **The user's resources stay on the user's machine.** Registering a codebase points at a path; it does not upload it. Indexing, artifacts, decks and history are all local. The only thing that ever leaves is the content of a bounded model call, and the user chose where that goes when they picked a path. Anything that quietly widens what leaves is a breach of the product, not an optimisation.

## Benchmarks

[benchmarks/](benchmarks/) is the home for measurement — one concern per target.

**Build the quality benchmark before refining anything.** Tuning without it is guessing.

The design on hand: codebases with an existing human-made architecture talk; compare what Standup chose against what the presenter actually covered. Initial target: 60% overlap, below which the selection logic is wrong and polish is irrelevant.

**That measures the onboarding case, not the recurring one.** Ground truth for "the right three things to say about my last two days" is unsolved — open question 2. Benchmark still comes first; what it measures needs settling before it is built.

Budgets for cost, latency, and memory get set from real measurement, not estimated now. Record them here once measured.

## Working agreements

- Any change touching selection → re-measure against the benchmark and report the delta. A quality gain that doubles cost is a decision to surface, not a win to claim.
- Prefer inference from the codebase over asking a model, wherever the answer is derivable.
- The evidence in SPECS establishes that comprehension is expensive and onboarding is slow. It does **not** establish that a deck is the remedy, and it does **not** cover the recurring-presentation framing at all — nobody has measured how often engineers present or what preparing costs them. Both gaps close with primary research, not more desk research. Don't treat either as settled.

## Open questions

**Nothing below is decided.** Don't pick one silently to unblock yourself — ask.

| # | Question | What it changes |
|---|---|---|
| 1 | **How does this ship as one command?** | Directly contradicts the current stack. Two services, a Python runtime, a Node build and a `d2` binary do not install with one command today. If the Python process serves the frontend, Next.js must be a **static export** — no SSR, no server components, no route handlers. That is a frontend architecture constraint, not a packaging detail. |
| 2 | **How long until a new user's first deck?** | Every deck after the first is cheap because the project is indexed. The first is not, and it lands exactly where someone decides whether to keep the tool — Gamma manages nothing-to-deck in under a minute. Indexing the recent window before the full history would help; nothing is measured. |
| 3 | Is BYOK single-provider or multi-provider? | Whether `src/llm/` normalises across wire formats or only ever speaks Anthropic. Presenton supports four; supporting one is far cheaper and may be enough. |
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
