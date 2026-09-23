<p align="center">
  <img src="public/standup.png" alt="Standup" width="280" height="280">
</p>

<p align="center">
  <img alt="macOS · Linux · Windows" src="https://img.shields.io/badge/macOS%20·%20Linux%20·%20Windows-555">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white">
  <img alt="Local-first" src="https://img.shields.io/badge/local--first-44cc11">
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-blue">
</p>

<h1 align="center">Standup</h1>

## Problem

You present all the time (standups, demos, reviews, handovers, school assessments) and the expensive and time consiming part is not really building the slides, it's deciding what are the important things to say. The evidence is scattered across commits, code, and various documents, and it can getting really confusing trying to peice them together in order to pick your presentation pointers. Standup makes this slide creation, scripting and presentations fast and easy to ace!

## How Standup works

```
INDEX → GATHER → SELECT → PRESENT
```

| Step | What it does |
|---|---|
| **Index** | Parses your resources into facts (symbols, imports, git history, what your docs emphasise). Offline, once per project. |
| **Gather** | Narrows that picture to what your request puts in play. |
| **Select** | Decides what belongs. This is the product. |
| **Present** | Writes one grounded narrative, composes editable slides, exports `.pptx`. |

An AI director makes the editorial cut; deterministic code supplies evidence, executes, and
validates. You see what was chosen and why *before* anything renders, and you correct it by talking.

## Performance

TBC :)

## Install

Requires Python 3.12+.

```powershell
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/v1-nce/standup/main/install.sh | sh

# Windows (PowerShell)
irm https://raw.githubusercontent.com/v1-nce/standup/main/install.ps1 | iex
```

On first run Standup asks for one model key in the browser and saves it for you. To do it by hand,
add the key to `~/.standup/.env` (`%USERPROFILE%\.standup\.env` on Windows):

```
MODEL_API_KEY=
```

## Use

```powershell
standup
```

Your browser opens at `http://127.0.0.1:8000`.

1. **Create a project** — *+ New project*, name it.
2. **Attach** — paste a folder path (or drop documents) in the *+* panel.
3. **Ask** — *"standup tomorrow, three slides on what changed this week."*
4. **Refine** — *"drop the second one,"* *"reword slide three."*
5. **Download** — export the `.pptx`.

