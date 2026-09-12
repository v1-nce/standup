# Standup

**Whatever you need to present → slide deck.**

You present your work all the time — standups, demos, reviews, handovers — and every time the hard
part is the same: deciding what to say. The evidence is scattered across the codebase, commits, and
documents, and by the time you sit down you don't know what actually mattered.

Standup closes that gap. Register your resources once, ask in plain language, and it decides what
belongs on the slides.

## How it works

```
INDEX → GATHER → SELECT → PRESENT
```

| Step | What it does |
|---|---|
| **Index** | Parses your resources into facts: symbols, dependencies, git history, what your own docs emphasise. Runs once per project, offline. |
| **Gather** | Narrows that picture to what your request puts in play. |
| **Select** | Decides what belongs. This is the product — the judgment no other tool does. |
| **Present** | Writes one grounded narrative and composes editable slides, exported as `.pptx`. |

Three things make it different from asking a chatbot:

- **It decides; you edit.** You see what was chosen and why *before* the deck exists, then correct it
  by talking — *"drop the second one,"* *"reword slide three, punchier."* Your correction is obeyed
  literally; slides you didn't mention keep their wording exactly.
- **Grounded in your own evidence.** Slides come from what actually changed — git history,
  dependencies, your documents — not a model's general memory.
- **Nothing leaves your machine.** Registering a codebase points at a *path*; it doesn't upload.
  Indexing, decks, and history stay local; only the model call leaves, to a provider you chose.

## Install

**Prerequisites:** Python 3.12+ (or [uv](https://docs.astral.sh/uv/) for a cleaner install that handles PATH).

One command:

```powershell
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/v1-nce/standup/main/install.sh | sh

# Windows (PowerShell)
irm https://raw.githubusercontent.com/v1-nce/standup/main/install.ps1 | iex
```

Then add a model key and run `standup` (next section).

## Add a model

Standup needs one model key before it can write. Create a file named `.env` inside a `.standup` folder
in your home directory — `~/.standup/.env` on macOS/Linux, `%USERPROFILE%\.standup\.env` on
Windows — with one line:

```
ANTHROPIC_API_KEY=sk-ant-...      # Claude
GEMINI_API_KEY=AIza...            # free to try
```

or any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, Ollama, LM Studio, vLLM):

```
OPENAI_API_KEY=...
LLM_BASE_URL=http://localhost:11434/v1   # omit for api.openai.com
LLM_MODEL=llama3.1                        # in that endpoint's naming
```

Leave `LLM_MODEL` empty to use the provider's default.

## Run it

```powershell
standup
```

Your browser opens at `http://127.0.0.1:8000`.

## Make a deck

1. **Create a project** — click *+ New project* in the left rail and name it.
2. **Attach what it should talk about** — click *+* above the chat: paste a folder path and **Add**,
   or drop documents / **Add file**. A folder is read where it lives; a document is copied in.
3. **Ask for a deck** — *"standup tomorrow, three slides on what changed this week."* The first
   request also indexes, so give it a few seconds.
4. **Change it by talking** — *"drop the second one,"* *"reword slide three, punchier."*
5. **Download** — export the `.pptx`; it opens and edits like any other deck in PowerPoint or Keynote.

## Status

Chat, decks, and the GUI work end to end and produce a real, editable `.pptx`. Not built yet:
diagrams, streaming progress, and the hosted subscription gateway.

## Troubleshooting

| Symptom | Fix |
|---|---|
| First run prints "Standup needs a model" | Expected — add a key to `~/.standup/.env`, then restart |
| `503` on any deck request | No model key — see "Add a model" |
| `502` on any deck request | The key reached the provider and was rejected — check it |
| `standup` not found | The installer used pip, which puts `standup` in a user-scripts folder — add it to your PATH (the installer prints the location), or install [uv](https://docs.astral.sh/uv/) first and re-run the install line |
