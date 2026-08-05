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

## Status

Backend only, 122 tests passing. Index, gather, select and present run end to end and produce a
`.pptx`. No frontend, no packaging, no diagrams, no benchmarks yet.

Run it: [backend/README.md](backend/README.md).

## Docs

| | |
|---|---|
| [docs/SPECS.md](docs/SPECS.md) | The product — problem, users, competitors, scope |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The system's shape and the bets behind it |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Prior art the design argues against |
| [docs/BEST_PRACTICES.md](docs/BEST_PRACTICES.md) | The standard the architecture answers to |
| [CLAUDE.md](CLAUDE.md) | Stack, rules, targets, and the canonical open questions |
| [backend/README.md](backend/README.md) | Install, run, test |
