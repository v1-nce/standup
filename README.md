# Standup

## 1. Introduction

People present their work far more often than they have time to prepare for it. Standups multiple times a
week. Sprint demos. Design reviews. Handovers. Onboarding. All of which require us to think of what to put into
our slides!

You have a rough idea of what you did, but evidence is scattered across the codebase, chat logs, discussions
and you end up not knowing what exactly is best to present at all.

**The expensive part of presenting isn't making slides. It's deciding what to say and how to say it.**

## 2. Description

You register your resources once — a codebase and its git history, documents, past decks — then
ask for a deck in plain language. Four steps run between your sentence and the file:

```
INDEX   →   GATHER   →   SELECT   →   PRESENT
(once)      (scope)      (decide)     (slides)
```

| Step | What it does | Model? |
|---|---|---|
| **Index** | Parses your resources into facts: symbols, dependency graph, git history, what your own docs emphasise. Content-keyed, so unchanged sources cost nothing and it runs once per project, not per deck. | No — offline and free |
| **Gather** | The AI director interprets the request and asks deterministic tools for the relevant evidence; it can redirect the search when the first view is insufficient. | Direction: yes; retrieval: no |
| **Select** | The director forms stories and makes the audience-specific editorial cut, optionally informed by tailored specialist memos. Code only exposes provenance and enforces constraints. | Yes — this is the core judgment |
| **Present** | The director writes one grounded narrative and chooses editable semantic visuals; deterministic tools apply the plan, validate it, and compile `.pptx`. | Composition: yes; execution: no |

**An AI orchestrator runs the four steps by talking to you** — the way Claude Code edits a file. It
remains the single owner of the request: it interprets intent, chooses tools, checks results, and
answers. Deterministic tools retrieve/index evidence, apply edits, render, and validate; they do
not replace semantic, editorial, narrative, or visual judgment. The director loop remains bounded
(**one call to chat, up to two to change a deck, up to five to build one — select, then cut, then write, then answer, with a spare round only to retry a rejected command**). Difficult decks may
reserve one additional parallel wave of normally 1–2 narrow specialist calls, all counted in the
turn's token/time/cost ceiling; routine work pays none of that overhead. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §8.2.

Three things make it different from asking a chatbot:

- **The AI directs; code supplies ingredients and executes.** Index, search, graph, git, document,
  render, and validation tools expose provenance-bearing facts and reliable capabilities. The
  director can ask a tailored evidence, counterevidence, audience, domain, or visual specialist to
  investigate one uncertainty, but only the director forms the story and writes the deck. This
  focuses model intelligence without paying for an uncontrolled committee.
- **The judgment is yours to edit, by saying so.** You see what was chosen and why *before* the
  deck exists. "Drop the second one." "Reword slide three." Your correction is turned into one
  exact operation and then obeyed — slides you didn't mention keep their wording byte for byte,
  and a drop-or-reorder costs no model call at all.
- **Nothing leaves your machine.** Registering a codebase points at a *path*; it does not upload
  it. Indexing, artifacts, decks and history are all local files. The only thing that ever
  leaves is the content of a bounded model call, to a provider you chose.

**Status.** Chat, deck and GUI work end to end and produce a real `.pptx` — 320 backend tests, 40
in the GUI. The benchmark harness is built; diagrams and packaging are not.

## 3. Folder Structure

```
standup/
├── pyproject.toml              the package; declares the `standup` command
├── README.md                   this file
├── .env.example                copy to .env, add one model key
│
├── src/standup/                THE PACKAGE — the only thing that ships
│   ├── cli.py                  `standup` → serve the GUI and open the browser
│   ├── config.py               settings; reads ~/.standup/.env before any repo .env
│   ├── errors.py               the one exception hierarchy
│   │
│   ├── core/                   the analysis library — knows nothing about the web
│   │   ├── agent/              the turn: bounded loop and deterministic deck operations
│   │   ├── index/              code.py · graph.py · history.py · docs.py
│   │   ├── gather.py           scope validation, then candidates. Deterministic
│   │   ├── selection/          signals.py · score.py · diversity.py
│   │   ├── present/            evidence.py · validate.py · deck.py
│   │   ├── llm/                the only path to a model; Anthropic + Gemini behind one interface
│   │   ├── projects/           projects on disk, chat log
│   │   ├── models/             artifacts.py — the pipeline's typed spine
│   │   └── pipeline.py         the deck on disk; every function deterministic
│   │
│   ├── api/                    FastAPI over core/, plus a static mount over web/
│   └── web/                    the built GUI, staged here by `npm run build`. GENERATED
│
├── ui/                         GUI SOURCE — Next.js, static export
│   ├── app/api/                fetch client + schema.d.ts, GENERATED from the backend
│   ├── app/                    the screens you edit
│   ├── __tests__/              vitest
│   └── out/                    Next's export, copied into web/. GENERATED
│
├── tests/                      pytest — 167 tests
├── benchmarks/                 measurement, one concern per target. Not built
└── docs/                       PRODUCT · SPECIFICATIONS · ARCHITECTURE · RESEARCH · UIUX · LOG
```

## 4. Quick Start

You need **Python 3.12+**, **Node 22+**, and **git**. Five steps, once.

### 1. Install Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Build the GUI

```powershell
cd ui
npm install
npm run build
cd ..
```

### 3. Add a model

Copy `.env.example` to `.env` and fill in **one** line:

```
ANTHROPIC_API_KEY=sk-ant-...
```

free while developing:

```
GEMINI_API_KEY=AIza...
```

or any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, Ollama, LM Studio, vLLM, ...):

```
OPENAI_API_KEY=...
LLM_BASE_URL=http://localhost:11434/v1   # or omit for api.openai.com
LLM_MODEL=llama3.1                       # the model, in that endpoint's naming
```

`LLM_MODEL` picks the model for whichever provider is active; leave it empty to use that
provider's default.

### 4. Start it!

```powershell
standup
```

Your browser opens at `http://127.0.0.1:8000`. Leave this terminal running and open a second one
for the commands below.

### 5. Make a deck

Everything happens in the browser window that just opened.

**Create your project.** Click *+ New project* in the left rail and name it. That is all a
project needs: a name, and the one deck it holds. Rename or delete it there later.

**Attach what it should talk about.** The `+` above the chat opens the context window. Paste a
folder's path and press **Add**; drop documents on the panel or pick them with **Add file**. Attach
as many as you like; each is indexed on its own and they are ranked together. Remove one and
everything derived from it goes with it.

Two ways in, because a browser is never told where a dropped file lives — a folder is named by its
path and read where it lives, a document is handed over whole and copied into the project, so
moving the original later never breaks a deck.

**Ask for a deck.** Type what you need in the chat, in plain English — *"standup tomorrow, three
slides on what changed this week"*. The first request also indexes the resources, so give it a few
seconds; later ones are fast.

Standup replies with what it chose and why, and the slides appear on the right.

**Change it by saying so.** *"Drop the second one."* *"Reword slide three, punchier."* *"Add
whatever touched the API."* Your correction is applied literally — slides you didn't mention keep
their wording exactly, and nothing you removed comes quietly back.

**Change content or design by saying so.** Standup can patch one slide, delete or reorder slides,
add grounded images and speaker notes, and compose freely with positioned text, vector shapes,
lines, typography, color, rotation and layering on a normalized canvas. It can also restyle the deck
with technical, light, dark, editorial or bold art direction. These are real agent operations, not
prompt-only wishes; every untouched slide field and visual layer stays exact.

**Get the file** at `127.0.0.1:8000/projects/PROJECT_ID/deck/file`. Open `deck.pptx` in
PowerPoint or Keynote and edit its native text boxes, shapes and images like any other deck.

### Working on Standup itself

```powershell
python -m pytest          # 320 tests
ruff check .

cd ui
npm run dev               # http://localhost:3000, hot reload; expects the API on :8000
npm test                  # 40 tests
```

In development the GUI runs on `:3000` and the API on `:8000` — two ports. A real install serves
both from one.

### If something goes wrong

| Symptom | Cause |
|---|---|
| `standup` not found | The venv isn't activated, or step 1 didn't finish |
| Browser shows raw JSON, no page | Step 2 was skipped — `src/standup/web/` doesn't exist yet |
| `503` from any deck request | No model key. See step 3 |
| `502` from any deck request | The key reached the provider and was rejected |
| `curl` asks about "Script Execution Risk" | You typed `curl` instead of `curl.exe` |

Full endpoint reference: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Design and rationale: [docs/](docs/).
