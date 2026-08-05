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
| **Gather** | Turns your sentence into a time window, a filter and a slide budget, then applies it to the index. | One call |
| **Select** | Ranks and cuts. Five signals, weighted, plus MMR so you don't get three slides on one file. | No — plain code |
| **Present** | Writes the slide text, checks every claim against the index, builds the `.pptx`. | One call |

**Two model calls per deck.** Everything between them is deterministic.

Three things make it different from asking a chatbot:

- **The model is never asked what's important.** Ask a model "which of these 40 things matter?"
  and it says "all of them" — that's the flat-output failure. It never sees the candidate list,
  the scores, or the cut. Your request steers *where to look*; code decides *what's good*.
- **The judgment is yours to edit.** You see what was chosen and why *before* the deck exists.
  Remove an item and it's gone; reorder and that order holds. Your edit is applied literally —
  nothing re-interprets it, and a drop-or-reorder rebuild costs no model call at all.
- **Nothing leaves your machine.** Registering a codebase points at a *path*; it does not upload
  it. Indexing, artifacts, decks and history are all local files. The only thing that ever
  leaves is the content of a bounded model call, to a provider you chose.

**Status.** The four steps work end to end and produce a real `.pptx` — 122 tests. The GUI is a
scaffold: it builds and is served, but the screens aren't written yet, so today you drive
Standup through its HTTP API. Diagrams, packaging and benchmarks are not built.

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
│   │   ├── index/              code.py · graph.py · history.py · docs.py
│   │   ├── gather.py           scope (one model call), then candidates
│   │   ├── selection/          signals.py · score.py · diversity.py
│   │   ├── present/            plan.py · validate.py · deck.py
│   │   ├── llm/                the only path to a model; Anthropic + Gemini behind one interface
│   │   ├── projects/           projects on disk, chat log
│   │   ├── models/             artifacts.py — the pipeline's typed spine
│   │   └── pipeline.py         the four steps, stitched
│   │
│   ├── api/                    FastAPI over core/, plus a static mount over web/
│   └── web/                    the built GUI, staged here by `npm run build`. GENERATED
│
├── ui/                         GUI SOURCE — Next.js, static export
│   ├── app/                    the screens you edit
│   ├── __tests__/              vitest
│   └── out/                    Next's export, copied into web/. GENERATED
│
├── tests/                      pytest — 122 tests
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

The GUI is still a scaffold, so for now you talk to Standup over HTTP. On Windows type
`curl.exe`, **not** `curl` — plain `curl` is a different PowerShell command and will not work.
On macOS/Linux drop the `.exe` and the `\` escapes.

**Register your project.** Point it at any folder with a git repo in it. Copy the `id` it prints.

```powershell
curl.exe -X POST 127.0.0.1:8000/projects -H "Content-Type: application/json" -d '{\"name\":\"My App\",\"location\":\"C:/Users/you/Dev/myapp\"}'
```

**Ask for a deck.** Say what you need in plain English. The first request also indexes the
repo, so give it a few seconds; later ones are fast.

```powershell
curl.exe -X POST 127.0.0.1:8000/projects/PROJECT_ID/decks -H "Content-Type: application/json" -d '{\"request\":\"standup tomorrow, what changed this week\",\"slide_budget\":3}'
```

You get back a `deck_id` and the **selection** — what it chose, what it cut, and the score
behind every item. This is the part worth reading.

**Change your mind** *(optional)*. List the ids you want, in the order you want them. Anything
you leave out is dropped, and you can pull something back up from the cut list.

```powershell
curl.exe -X PUT 127.0.0.1:8000/projects/PROJECT_ID/decks/DECK_ID/selection -H "Content-Type: application/json" -d '{\"keep\":[\"src/auth.py\",\"src/api.py\"]}'
```

**Get the file.**

```powershell
curl.exe -X POST 127.0.0.1:8000/projects/PROJECT_ID/decks/DECK_ID/build --output deck.pptx
```

Open `deck.pptx` in PowerPoint or Keynote and edit it like any other deck.

### Working on Standup itself

```powershell
python -m pytest          # 122 tests
ruff check src tests

cd ui
npm run dev               # http://localhost:3000, hot reload; expects the API on :8000
npm test
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
