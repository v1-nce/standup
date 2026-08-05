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
| **Gather** | Turns your sentence into a time window, a filter and a slide budget, then applies it to the index. | No — the agent already read your sentence |
| **Select** | Ranks and cuts. Five signals, weighted, plus MMR so you don't get three slides on one file. | No — plain code |
| **Present** | Writes the slide text, checks every claim against the index, builds the `.pptx`. | No — the agent writes it |

**An agent runs the four steps by talking to you** — the way Claude Code edits a file. It names an
operation, the operation runs in code, it sees what happened, then it answers. Nothing else calls
a model, so the whole bill is the conversation: **one call to chat, two to change a deck, three to
build one.**

Three things make it different from asking a chatbot:

- **The model is never asked what's important.** Ask a model "which of these 40 things matter?"
  and it says "all of them" — that's the flat-output failure. It never sees the scores or the
  signals. Your request steers *where to look*; code decides *what's good*.
- **The judgment is yours to edit, by saying so.** You see what was chosen and why *before* the
  deck exists. "Drop the second one." "Reword slide three." Your correction is turned into one
  exact operation and then obeyed — slides you didn't mention keep their wording byte for byte,
  and a drop-or-reorder costs no model call at all.
- **Nothing leaves your machine.** Registering a codebase points at a *path*; it does not upload
  it. Indexing, artifacts, decks and history are all local files. The only thing that ever
  leaves is the content of a bounded model call, to a provider you chose.

**Status.** Chat, deck and GUI work end to end and produce a real `.pptx` — 140 backend tests, 15
in the GUI. Adding context beyond the codebase (the `+` button), diagrams, packaging and
benchmarks are not built.

## 3. Folder Structure

```
standup/
├── pyproject.toml              the package; declares the `standup` command
├── README.md                   this file
├── API.md                      every endpoint, input and output
├── .env.example                copy to .env, add one model key
│
├── src/standup/                THE PACKAGE — the only thing that ships
│   ├── cli.py                  `standup` → serve the GUI and open the browser
│   ├── config.py               settings; reads ~/.standup/.env before any repo .env
│   ├── errors.py               the one exception hierarchy
│   │
│   ├── core/                   the analysis library — knows nothing about the web
│   │   ├── agent/              the turn: the loop, and the three commands it may name
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
├── tests/                      pytest — 140 tests
├── benchmarks/                 measurement, one concern per target. Not built
└── docs/                       SPECS · ARCHITECTURE · RESEARCH · UIUX
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

### 3. Add a model key

Copy `.env.example` to `.env` and fill in **one** line:

```
ANTHROPIC_API_KEY=sk-ant-...
```

or, free while developing:

```
GEMINI_API_KEY=AIza...
```

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

**Attach what it should talk about.** The `+` above the chat is where a repository, a PDF or a
document gets registered against the project. **This is not built yet** — until it is, a project
created in the GUI has nothing to draw on, and the agent will say so rather than invent a deck.

**Ask for a deck.** Type what you need in the chat, in plain English — *"standup tomorrow, three
slides on what changed this week"*. The first request also indexes the resources, so give it a few
seconds; later ones are fast.

Standup replies with what it chose and why, and the slides appear on the right.

**Change it by saying so.** *"Drop the second one."* *"Reword slide three, punchier."* *"Add
whatever touched the API."* Your correction is applied literally — slides you didn't mention keep
their wording exactly, and nothing you removed comes quietly back.

**Get the file** at `127.0.0.1:8000/projects/PROJECT_ID/deck/file`. Open `deck.pptx` in
PowerPoint or Keynote and edit it like any other deck.

### Working on Standup itself

```powershell
python -m pytest          # 140 tests
ruff check .

cd ui
npm run dev               # http://localhost:3000, hot reload; expects the API on :8000
npm test                  # 15 tests
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

Full endpoint reference: [API.md](API.md). Design and rationale: [docs/](docs/).
