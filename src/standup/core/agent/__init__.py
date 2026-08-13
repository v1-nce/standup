"""The turn: the model reads the conversation, changes the deck, and answers. One loop, one caller."""

from datetime import UTC, datetime

from pydantic import BaseModel

from standup.core import pipeline
from standup.core.agent.commands import Command, apply
from standup.core.llm import ModelClient
from standup.core.models import ChatMessage, Deck, Index
from standup.core.present import evidence
from standup.core.projects import ProjectStore
from standup.errors import NotFound

MAX_ROUNDS = 5

SYSTEM = """You are Standup. You build and improve one slide deck per project by talking to the
person who will present it, and you answer them the way a colleague would.

Put any change to the deck in `commands`, and leave `commands` empty once the deck needs no more
work - that ends the turn. `reply` is what the person reads, so write it only on the round you
leave `commands` empty; while you are still working, leave `reply` empty too.

You do not decide what matters. Ranking is computed from the repository itself: what changed,
what depends on what, what the project's own writing stresses. Your job is to set the search,
obey corrections literally, and write the words.

COMMANDS

select - re-derive the deck from a scope. Use it for a new request or a changed window. It
discards slides written against the old scope.
  request: what the person asked, in their words.
  scope.since, scope.until: the window the request implies; omit both if it implies none.
  scope.paths: file or directory fragments the request names; omit if it names none.
  scope.keywords: distinctive terms worth matching against code and commit messages. Ordinary
    words - update, work, stuff, things - are not keywords.
  scope.audience: who the deck is for, if the request says.
  scope.slide_budget: how many slides were asked for, or 5 if the request is silent.

keep - the exact ids the deck should hold, in the order they should appear. Anything left out is
cut. This is how you drop, reorder, or bring something back from the cut list. Free slide ids
belong in this list too, interleaved wherever they should sit among the evidence slides.

write - slide text, one entry per slide you are changing. Slides you leave out keep their current
wording exactly.
  title: a short phrase naming the item. Not a sentence.
  bullets: two to four short lines, each saying something the evidence supports.
  Never name a file, function or module that is not in that item's evidence. Describe what
  changed rather than showing code.
  free: set this true for a slide with no evidence behind it - a title slide, a section break, or
  exact wording the person dictated - and invent a short, stable id for it so it can be moved or
  edited later. A free slide is not checked against the index, so the restraint is yours: write
  only what was asked, nothing more. Asked for a title and nothing else, leave bullets empty -
  do not invent lines to fill the slide out. It lands after the evidence slides unless you place
  it with `keep`.

Every path begins with the resource it came from - an attached folder or file - not a directory
of it. Keep that first segment when you name a path, and never mix two resources on one slide.

There is no command to produce the file: the slides are the deck, and the `.pptx` is written when
it is downloaded.

A rejected command comes back as a result line. Read it and correct course; do not repeat it."""


def _deck_state(deck: Deck | None) -> str:
    if deck is None:
        return "DECK\nnone yet"

    written = {slide.candidate_id for slide in deck.slides or []}
    audience = deck.selection.scope.audience
    lines = [
        f'DECK (request: "{deck.selection.request}"'
        + (f", audience: {audience}" if audience else "")
        + ")",
        "chosen:",
    ]
    lines += [
        f"  {entry.candidate.id}"
        + (" [slide written]" if entry.candidate.id in written else " [no slide]")
        for entry in deck.selection.chosen
    ]
    if deck.selection.cut:
        lines += ["cut:"] + [f"  {entry.candidate.id}" for entry in deck.selection.cut]
    frees = [slide for slide in deck.slides or [] if slide.free]
    if frees:
        lines += ["free:"] + [f"  {slide.candidate_id}: {slide.title}" for slide in frees]
    return "\n".join(lines)


def _prompt(
    store: ProjectStore,
    project_id: str,
    index: Index | None,
    history: list[ChatMessage],
    results: list[str],
    today: datetime,
    *,
    last: bool,
) -> str:
    """Stable first, volatile last, so a cached prefix stays a prefix when caching lands."""
    try:
        deck: Deck | None = pipeline.read(store, project_id)
    except NotFound:
        deck = None

    oldest = min((commit.authored_at for commit in index.commits), default=None) if index else None
    facts = "PROJECT\n" + (
        f"{len(index.files)} files indexed, {len(index.commits)} commits"
        + (f" back to {oldest.date().isoformat()}" if oldest else "")
        if index
        else "Nothing attached yet, so no deck can be built. Say so if one is asked for"
    )
    said = "\n".join(f"{message.role}: {message.content}" for message in history)
    blocks = [
        f"{facts}. Today is {today.date().isoformat()}.",
        _deck_state(deck),
        f"EVIDENCE\n{evidence(deck.selection, index) if deck and index else ''}",
        f"CONVERSATION\n{said}",
    ]
    if results:
        blocks.append("RESULTS THIS TURN\n" + "\n".join(results))
    if last:
        blocks.append("LAST ROUND\nNo further commands will be run. Answer now with what stands.")
    return "\n\n".join(blocks)


class Turn(BaseModel):
    """What the model returns each round. No commands means the turn is over."""

    reply: str
    commands: list[Command] = []


async def converse(
    client: ModelClient,
    store: ProjectStore,
    project_id: str,
    history: list[ChatMessage],
    *,
    today: datetime | None = None,
) -> str:
    """Answer the last message, changing the deck as the conversation requires."""
    index = await pipeline.indexed(store, project_id)
    when = today or datetime.now(UTC)
    results: list[str] = []

    async def ask(*, last: bool) -> Turn:
        prompt = _prompt(store, project_id, index, history, results, when, last=last)
        return await client.structured(prompt, Turn, system=SYSTEM)

    for _ in range(MAX_ROUNDS - 1):
        turn = await ask(last=False)
        if not turn.commands:
            return turn.reply
        results += [apply(store, project_id, index, command) for command in turn.commands]

    # Out of budget. Asking for an answer beats raising, which would throw away work already done.
    return (await ask(last=True)).reply
