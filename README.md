# Standup

**Whatever you need to present → slide deck.**

You register your resources once — a codebase and its git history, documents, past decks — then
chat to ask for a deck. Standup works out what happened, decides which two or three things
deserve the room's attention, shows you that decision so you can correct it, and builds the
slides.

The expensive part of presenting isn't making slides. It's deciding what to say, and no tool
does that because every tool assumes you already know. **Selection is the product.**

Everything stays on your machine. Registering a codebase points at a path; it does not upload
it. The only thing that leaves is the content of a bounded model call, to a provider you chose.

## How it works

```
INDEX  →  GATHER  →  SELECT  →  PRESENT
(once)    (scope)    (decide)   (slides)
```

**Index** parses your resources into derived facts — symbols, dependency graph, git history,
what your own docs emphasise. No model, no network, and content-keyed so unchanged sources cost
nothing. **Gather** turns your sentence into a window and a filter, then applies it. **Select**
ranks and cuts in plain code — the model is never asked what matters, because asked directly it
answers "all of it". **Present** turns the selection into slides, validated against the index.

Two model calls per deck in the steady state.

## Layout

One installable Python package. The UI is source that compiles into it, not a second service.

```
pyproject.toml        the package; declares the `standup` command
src/standup/
  cli.py              `standup` — serve the GUI and open it
  config.py           settings; reads ~/.standup/.env before any repo .env
  errors.py           the one exception hierarchy
  core/               the analysis library — imports nothing from api/ or the web
    index/            walk, parse, import graph, git history, doc emphasis
    gather.py         scope (one model call), then candidates
    selection/        signals, weights, MMR — no model reaches this decision
    present/          plan (one model call), validate, build the .pptx
    llm/              the only path to a model; nothing outside names a provider
    projects/         projects on disk, chat log
    models/           the pipeline's typed spine
    pipeline.py       the four stages, stitched
  api/                FastAPI over core/, plus a StaticFiles mount over web/
  web/                built GUI, staged here by `npm run build`. Generated
ui/                   GUI source — Next.js static export
tests/                pytest
benchmarks/           measurement, one concern per target
```

## Run it

Requires Python 3.12+, Node 22+, and `git`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

cd ui && npm install && npm run build && cd ..
standup
```

`standup` serves the API and the GUI from one process and opens your browser.
`--port` and `--no-browser` are the only flags.

Connect a model by putting one key in `~/.standup/.env` (or the repo's `.env` while developing):

```
ANTHROPIC_API_KEY=sk-ant-...     # or
GEMINI_API_KEY=AIza...
```

Anthropic wins if both are set; `LLM_PROVIDER=gemini` overrides that. Indexing a project needs
no key — only writing slides does.

## Develop

```powershell
python -m pytest          # 122 tests
ruff check src tests

cd ui
npm run dev               # http://localhost:3000, expects the API on :8000
npm test
```

In dev the GUI runs on `:3000` and the API on `:8000`, which is cross-origin — the API allows
that one origin. A packaged install serves both from one port and never uses it.

API reference: [API.md](API.md).

## Docs

| | |
|---|---|
| [docs/SPECS.md](docs/SPECS.md) | The product — problem, users, competitors, scope |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The system's shape and the bets behind it |
| [docs/UIUX.md](docs/UIUX.md) | How someone installs and uses it |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Prior art the design argues against |
| [CLAUDE.md](CLAUDE.md) | Stack, rules, targets, and the canonical open questions |
