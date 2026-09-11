"""The turn: the model reads the conversation, changes the deck, and answers. One loop, one caller."""

import asyncio
import re
from datetime import UTC, datetime

from pydantic import BaseModel

from standup.core import pipeline
from standup.core.agent.commands import Command, Style, Update, Write, apply, echo
from standup.core.llm import ModelClient
from standup.core.models import (
    ChatMessage,
    Deck,
    Index,
    Memory,
    Scope,
    Slide,
    SlidePlan,
)
from standup.core.present import evidence, order_fault
from standup.core.present.preview import contact_sheet
from standup.core.projects import ChatLog, ProjectStore
from standup.errors import NotFound, StandupError

# A director build is select (scope + shortlist) -> keep (cut) -> write -> answer, four calls on the
# happy path. One round above that is the recovery budget: a rejected command (a batched keep+write,
# a mistyped id) must not turn a build that was one correction away from writing into a failure.
MAX_ROUNDS = 5
MAX_HISTORY_MESSAGES = 12
MAX_PROMPT_EXCERPTS = 8
PROMPT_EXCERPT_CHARS = 800
MAX_CONTEXT_RESOURCES = 20
# The head of a selection's cut list the prompt shows. `keep` may bring back any candidate it can
# still name, so only the near-misses belong in the prompt - dumping the whole pool (often hundreds
# of ids, ranked and never read) is the largest single block in the prompt. `choose` orders `cut` by
# score descending and `edited` puts the just-cut shortlist first, so the head is exactly those.
MAX_CUT_CANDIDATES = 20
MAX_PREFERENCES = 15
# The model's own working memory, carried between rounds. Bounded on the way back in so a verbose
# model can't inflate every later round's prompt.
MAX_NOTES_CHARS = 800
_TERM = re.compile(r"[a-z0-9_.-]{3,}")
_BORING_TERMS = {"about", "attached", "document", "file", "files", "tell", "what", "with"}

SYSTEM = """You are Standup. You build and improve one slide deck per project by talking to the
person who will present it, and you answer them the way a colleague would.

Put a deck change in `commands`, with exactly one command per round. The command runs before you
see the next round, so never guess the result of `select` and never batch operations against stale
state. Set `changes_deck` true whenever the person asked to create or change the deck, even if you
cannot name a command yet. Leave `commands` empty once the deck needs no more work. `notes` is your
private working memory: while working, write a few sentences on your plan, what you just decided and
why, and what remains, so the next round can pick up where you left off. `reply` is what the person
reads, so write it only with empty `commands`; while working, leave it empty too.
For ordinary questions about the project or attached context, answer directly with no commands and
set `changes_deck` false.

Ranking surfaces a shortlist of candidates from the repository itself: what changed, what
depends on what, what the project's own writing stresses. You decide what matters: after `select`
returns that shortlist, make the final cut with `keep`, then write the words. Obey corrections
literally.

COMMANDS

select - re-derive the deck from a scope. Use it for a new request or a changed window. It
returns a shortlist of about three times `scope.slide_budget` candidates; you then make the
final cut with `keep`. It discards slides written against the old scope.
  request: what the person asked, in their words.
  scope.since, scope.until: the window the request implies; omit both if it implies none.
  scope.paths: file or directory fragments the request names; omit if it names none.
  scope.keywords: distinctive terms worth matching against code and commit messages. Ordinary
    words - update, work, stuff, things - are not keywords.
  scope.audience: who the deck is for, if the request says.
  scope.slide_budget: the final number of evidence slides the deck should hold, or 5 if the
    request is silent. `select` returns about three times this many candidates; cut to exactly
    this many with `keep`. A free slide is additional, not one of these slots, and every kept
    candidate still needs its own slide.

keep - the exact ids the deck should hold, in the order they should appear. After `select`, this
is how you make the final cut from the shortlist; anything left out is cut. It also drops,
reorders, or brings something back from the cut list. Free slide ids
belong in this list too, interleaved wherever they should sit among the evidence slides - but only
once `write` has given that id a slide. `keep` places slides, it does not create them.

write - create or replace complete slides. Slides you leave out remain byte-for-byte unchanged.
It may also set `design` while creating a deck, avoiding a separate styling round.
  Put the story in the outline: title, subtitle, bullets, secondary content, image and speaker_notes.
  `elements` is optional. Leave it empty and the renderer composes a clean layout from the outline;
  pick its shape with `layout` (cover, section, content, two_column, statement, image). Author
  `elements` only when you want a specific composition, which overrides the composed layout.
  Each element needs a stable id, kind, x, y, width and height. Coordinates are percentages.
    text: text, color, font_size (6-96), font_weight, optional font_family, align and valign.
    shape: rectangle, rounded, ellipse, triangle or chevron; fill, stroke and stroke_width.
    line: a vector from x,y by width,height; stroke and stroke_width. Width or height may be zero.
    image: an attached image id copied exactly from RELEVANT INDEXED EXCERPTS.
  Colors may be #RRGGBB or theme tokens: background, surface, text, muted, accent, on_accent,
  transparent. Later elements paint above earlier ones. Rotation is available on every layer.
  Compose, do not decorate a template: establish one visual idea, strong hierarchy, deliberate
  alignment and negative space. Use shapes, scale, asymmetry and layering when they clarify the
  story. Do not add furniture merely to fill the canvas, and keep text readable rather than dense.
  free is true only when no selected evidence backs the slide. Evidence-slide outline and canvas
  text must remain grounded; never name a file or function the project does not have.

update - patch one existing slide without resending it. Name slide_id and only fields to change.
`upsert_elements` replaces matching stable element ids or appends new layers; `remove_element_ids`
deletes layers. Everything omitted stays exact. clear_image removes the outline image.

style - replace deck-level art direction without touching slide content. design.theme is technical,
light, dark, editorial, or bold. An optional #RRGGBB accent and heading/body font names customize it.
Use `write.design` while creating a deck so the bounded turn still has room to finish slides.

Every path begins with the resource it came from - an attached folder or file - not a directory
of it. Keep that first segment when you name a path, and never mix two resources on one slide.

There is no command to produce the file: the slides are the deck, and the `.pptx` is written when
it is downloaded.

A rejected command comes back as a result line. Read it and correct course; do not repeat it."""


def _slide_text(slide: Slide) -> str:
    body = " / ".join(slide.bullets)
    secondary = " / ".join(slide.secondary_bullets)
    text = f'"{slide.title}"' + (f" - {body}" if body else "")
    details = [f"layout: {slide.layout}"]
    if slide.subtitle:
        details.append(f"subtitle: {slide.subtitle}")
    if secondary:
        details.append(f"secondary: {slide.secondary_title}: {secondary}")
    if slide.image:
        details.append(f"image: {slide.image}")
    if slide.speaker_notes:
        details.append("speaker notes present")
    if slide.elements:
        details.append(
            "canvas: " + "; ".join(
                element.model_dump_json(exclude_none=True) for element in slide.elements
            )
        )
    return f"{text} [{' | '.join(details)}]"

def _scope_state(scope: Scope) -> str:
    parts = [f"{scope.slide_budget} slides"]
    if scope.since:
        parts.append(f"since {scope.since.date().isoformat()}")
    if scope.until:
        parts.append(f"until {scope.until.date().isoformat()}")
    if scope.keywords:
        parts.append(f"keywords {', '.join(scope.keywords)}")
    if scope.paths:
        parts.append(f"paths {', '.join(scope.paths)}")
    if scope.audience:
        parts.append(f"for {scope.audience}")
    return " | ".join(parts)


def _deck_state(deck: Deck | None) -> str:
    if deck is None:
        return "DECK\nnone yet"

    written = {slide.candidate_id: slide for slide in deck.slides or []}
    lines = [
        f'DECK (request: "{deck.selection.request}")',
        f"design: {deck.design.theme}"
        + (f" | accent {deck.design.accent}" if deck.design.accent else "")
        + f" | {deck.design.heading_font} / {deck.design.body_font}",
        # The standing scope, echoed back. It was write-only before, so "make it three slides
        # instead" meant re-deriving a window and keywords the model could no longer see.
        f"scope: {_scope_state(deck.selection.scope)}",
    ]

    if deck.slides is not None and not _missing_evidence_slides(deck):
        # Complete: `deck.slides` is the one true render order, evidence and free interleaved.
        # Showing it as two separate lists (evidence order, then a free bucket) hid where a free
        # slide actually sits - "the last slide" became ambiguous between "last of chosen" and
        # "last of free", and a `keep` built on that guess moved more than the one slide asked for.
        lines.append("order (top to bottom, exactly as it renders):")
        lines += [
            f"  {position}. {slide.candidate_id}"
            + (" [free]" if slide.free else "")
            + f" {_slide_text(slide)}"
            for position, slide in enumerate(deck.slides, start=1)
        ]
    else:
        lines.append("chosen:")
        lines += [
            f"  {entry.candidate.id}"
            + (
                f" [slide written] {_slide_text(written[entry.candidate.id])}"
                if entry.candidate.id in written
                else " [no slide]"
            )
            for entry in deck.selection.chosen
        ]
        frees = [slide for slide in deck.slides or [] if slide.free]
        if frees:
            lines += ["free:"] + [f"  {slide.candidate_id}: {_slide_text(slide)}" for slide in frees]

    if deck.selection.cut:
        visible = deck.selection.cut[:MAX_CUT_CANDIDATES]
        lines += ["cut:"] + [f"  {entry.candidate.id}" for entry in visible]
        hidden = len(deck.selection.cut) - len(visible)
        if hidden:
            lines.append(f"  … {hidden} more cut")
    return "\n".join(lines)


def _latest_user(history: list[ChatMessage]) -> str:
    return next((m.content for m in reversed(history) if m.role == "user"), "")


def _terms(history: list[ChatMessage]) -> set[str]:
    return {term for term in _TERM.findall(_latest_user(history).lower()) if term not in _BORING_TERMS}


def _missing_evidence_slides(deck: Deck | None) -> list[str]:
    if not deck:
        return []
    written = {slide.candidate_id for slide in deck.slides or [] if not slide.free}
    return [entry.candidate.id for entry in deck.selection.chosen if entry.candidate.id not in written]


_NO_DECK = "No deck command completed."
_NO_MATCHES = "The last select matched no candidates."
_NOTHING_RAN = "No command ran, though the message reads like a request to change the deck."
_NOTHING_SAID = "I don't have anything to add to that."
_DONE = "Done - the deck is ready."

_BLOCKED_REPLY = {
    _NO_DECK: "I couldn't create the deck because no deck command completed.",
    _NO_MATCHES: "I couldn't create the deck because that request matched nothing to build slides from.",
    _NOTHING_RAN: "I didn't manage to make that change to the deck.",
}


def _deck_blocker(deck: Deck | None) -> str | None:
    """None once the deck is complete. Otherwise a line naming what's wrong - `_NO_DECK` and
    `_NO_MATCHES` are dead ends (nothing to build from), but a named missing slide is fixable, and
    the caller treats it differently: one more real attempt before giving up, not an immediate one."""
    if deck is None:
        return _NO_DECK
    if not deck.selection.chosen:
        return _NO_MATCHES
    missing = _missing_evidence_slides(deck)
    if missing:
        names = ", ".join(item.split("/")[-1] for item in missing)
        return f"still needs evidence slides for: {names}"
    fault = order_fault(deck.slides or [], deck.selection)
    if fault:
        return fault
    return None


def _blocked_reply(blocker: str) -> str:
    # The three fixed reasons get their own wording; anything else is `_deck_blocker`'s own
    # sentence, already specific (which slide, not just "some slide") - showing it beats a canned
    # line that used to throw that detail away.
    return _BLOCKED_REPLY.get(blocker, f"I couldn't finish the deck - {blocker}.")


def _blocker_note(blocker: str) -> str:
    """Tell the next bounded round exactly what remains to be done."""
    if blocker == _NO_DECK:
        return "No deck command ran. Run select, keep, then write before answering."
    if blocker in (_NO_MATCHES, _NOTHING_RAN):
        return blocker
    return f"The deck {blocker}. Write it now."


def _write_blocker(current: Deck | None, command: Command) -> str | None:
    """Slides must wait for `keep`: a `select` leaves an uncut shortlist, and writing against it
    (three of eighteen candidates, say) is how a deck ends up "still needs evidence slides" for a
    dozen candidates the model never intended to finish."""
    if current is None or not isinstance(command, Write):
        return None
    wanted = len(current.selection.chosen)
    budget = current.selection.scope.slide_budget
    if wanted > budget:
        return (
            f"{echo(command)} rejected: select returned {wanted} candidates; "
            f"cut to {budget} with keep before writing slides"
        )
    return None


async def _visual_review(client: ModelClient, deck: Deck | None) -> str:
    """Render the deck and ask the model to critique its own work — the eyes-and-ears step. Skipped
    for clients that cannot see images, and on any render or vision failure: a review is a bonus,
    never a reason to fail the turn."""
    describe = getattr(client, "describe_image", None)
    if describe is None or not deck or not deck.slides:
        return ""
    plan = SlidePlan(design=deck.design, slides=deck.slides)
    try:
        png = await asyncio.to_thread(contact_sheet, plan)
        return await describe(
            png,
            "image/png",
            prompt=(
                "This is the current slide deck. In 2-3 sentences, critique its visual quality: "
                "hierarchy, readability, density, and anything that looks unfinished or off."
            ),
        )
    except StandupError:
        return ""


def _indexed_excerpts(index: Index | None, history: list[ChatMessage]) -> str:
    if not index:
        return ""
    terms = _terms(history)
    available = [facts for facts in index.files if facts.excerpt]
    matched = [
        facts
        for facts in available
        if not terms or any(term in f"{facts.path} {facts.excerpt}".lower() for term in terms)
    ]
    # ponytail: wording that shares no literal term with anything indexed falls back to whatever
    # comes first, rather than showing nothing — a rank-ordered fallback is the upgrade if that
    # proves too arbitrary.
    blocks = []
    for facts in (matched or available)[:MAX_PROMPT_EXCERPTS]:
        text = " ".join(facts.excerpt.split())[:PROMPT_EXCERPT_CHARS]
        blocks.append(f"id: {facts.path}\ntext: {text}")
    return "\n\n".join(blocks)


def _sources(store: ProjectStore, project_id: str, deck: Deck) -> dict[str, str]:
    """The current text of every chosen file. Read per round because a `select` changes who is
    chosen, and a handful of small reads is nothing beside the model call they inform."""
    return pipeline.sources(
        store,
        project_id,
        [path for entry in deck.selection.chosen for path in entry.candidate.paths],
    )


def _resources(store: ProjectStore, project_id: str) -> str:
    return "\n".join(
        f"{resource.kind.value}: {resource.name} (id: {resource.id})"
        for resource in store.get(project_id).resources[:MAX_CONTEXT_RESOURCES]
    )


def _preferences(memory: Memory) -> str:
    """A bounded reminder of what earlier decks kept and cut, so the director can reuse the
    project's own editorial history. Latest decision wins for a candidate: kept, then cut, then kept
    again reads as kept - a running tally would double-count every reorder."""
    if not memory.entries:
        return ""
    kept: list[str] = []
    cut: list[str] = []
    for entry in memory.entries:
        for item in entry.kept:
            if item in cut:
                cut.remove(item)
            if item not in kept:
                kept.append(item)
        for item in entry.cut:
            if item in kept:
                kept.remove(item)
            if item not in cut:
                cut.append(item)
    lines = []
    if kept:
        lines.append("kept: " + ", ".join(kept[:MAX_PREFERENCES]))
    if cut:
        lines.append("cut: " + ", ".join(cut[:MAX_PREFERENCES]))
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
    may_command: bool = False,
    notes: str = "",
    review: bool = False,
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
    recent = history[-MAX_HISTORY_MESSAGES:]
    said = "\n".join(f"{message.role}: {message.content}" for message in recent)
    cited = ""
    if deck and index:
        # The cut is the turn's highest-leverage decision; the model must see what each shortlist
        # candidate actually says before it throws it away. Ids and symbols alone starve it.
        cited = evidence(deck.selection, index, _sources(store, project_id, deck))
    preferences = _preferences(pipeline.memory(store, project_id)) if deck else ""
    blocks = [
        # Stable across every round of this turn - changes only between turns, if at all.
        f"{facts}. Today is {today.date().isoformat()}.",
        f"CONTEXT RESOURCES\n{_resources(store, project_id)}",
        f"RELEVANT INDEXED EXCERPTS\n{_indexed_excerpts(index, history)}",
        f"CONVERSATION\n{said}",
        # Volatile: a command applied last round changes both of these before the next one is asked.
        _deck_state(deck),
    ]
    if preferences:
        blocks.append(f"PREFERENCES\n{preferences}")
    blocks.append(f"EVIDENCE\n{cited}")
    if notes:
        blocks.append(f"YOUR NOTES\n{notes[:MAX_NOTES_CHARS]}")
    if results:
        blocks.append("RESULTS THIS TURN\n" + "\n".join(results))
    if last:
        if review:
            blocks.append(
                "VISUAL REVIEW ROUND\nA visual review just ran. If it flagged anything worth "
                "fixing, run one update, write, or style command now; otherwise answer."
            )
        elif may_command:
            blocks.append(
                "FINAL OPERATIONAL ROUND\nThe deck is incomplete. Exactly one command can still run. "
                "Run it now if it can finish the deck; otherwise answer honestly."
            )
        else:
            blocks.append("LAST ROUND\nNo further commands will be run. Answer now with what stands.")
    return "\n\n".join(blocks)


class Turn(BaseModel):
    """One bounded decision: one operation, or an answer."""

    reply: str = ""
    changes_deck: bool = False
    commands: list[Command] = []
    notes: str = ""


async def converse(
    client: ModelClient,
    store: ProjectStore,
    project_id: str,
    history: list[ChatMessage],
    *,
    today: datetime | None = None,
    log: ChatLog | None = None,
) -> str:
    """Answer the last message, changing the deck as the conversation requires.

    `log`, when given, is where each round's command outcomes are persisted as they happen - the
    same lines `results` carries within this turn, kept past it. Without a persisted record, a later
    turn can only read the model's own reply, which may say a command succeeded when it didn't; `log`
    is what lets it read back what actually ran.
    """
    index = await pipeline.indexed(store, project_id)
    when = today or datetime.now(UTC)
    results: list[str] = []
    notes = ""
    changed = False
    change_expected = False
    stalled = False
    reviewed = False
    review_pending = False

    async def ask(*, last: bool, may_command: bool, notes: str, review: bool = False) -> Turn:
        prompt = await asyncio.to_thread(
            _prompt, store, project_id, index, history, results, when, last=last, may_command=may_command, notes=notes, review=review
        )
        return await client.structured(prompt, Turn, system=SYSTEM)

    async def deck() -> Deck | None:
        try:
            return await asyncio.to_thread(pipeline.read, store, project_id)
        except NotFound:
            return None

    async def record(outcome: str) -> None:
        if log is not None:
            await asyncio.to_thread(log.append, "command", outcome)

    for round_number in range(MAX_ROUNDS):
        current = await deck()
        blocker = _deck_blocker(current) if changed else None
        complete = changed and blocker is None
        final_operation = not complete and round_number == MAX_ROUNDS - 1
        review = complete and review_pending
        last = complete or final_operation
        turn = await ask(last=last, may_command=final_operation or review, notes=notes, review=review)
        notes = turn.notes
        change_expected = change_expected or turn.changes_deck or bool(turn.commands)

        if review and not turn.commands:
            # The deck is complete; the model chose to answer rather than act on the critique.
            return turn.reply or _DONE

        if last and not final_operation and not review:
            if complete:
                return turn.reply or _DONE
            if change_expected:
                reason = _deck_blocker(current) if changed else _NOTHING_RAN
                return _blocked_reply(reason or _NOTHING_RAN)
            return turn.reply or _NOTHING_SAID

        if not turn.commands:
            if not change_expected or index is None:
                return turn.reply or _NOTHING_SAID
            if final_operation:
                return _blocked_reply(blocker or _NOTHING_RAN)
            if stalled:
                return _blocked_reply(blocker or _NOTHING_RAN)
            stalled = True
            results.append(_blocker_note(blocker or _NOTHING_RAN))
            continue

        review_pending = False  # the review shot is consumed by any command attempt

        if len(turn.commands) != 1:
            if final_operation:
                return _blocked_reply(blocker or _NOTHING_RAN)
            stalled = True
            results.append(
                f"commands rejected: expected exactly one operation, got {len(turn.commands)}"
            )
            continue

        command = turn.commands[0]
        blocked = _write_blocker(current, command)
        outcome = blocked if blocked is not None else await asyncio.to_thread(apply, store, project_id, index, command)
        await record(outcome)
        results.append(outcome)
        if outcome.startswith(f"{echo(command)} rejected:"):
            stalled = True
        else:
            changed = True
            stalled = False

        current = await deck()
        blocker = _deck_blocker(current) if changed else None
        # Only content changes are worth rendering and looking at. A reorder or re-selection
        # (`keep`/`select`) changes no pixels, so paying for an image review after one is waste.
        if (
            changed
            and blocker is None
            and not reviewed
            and isinstance(command, (Write, Update, Style))
        ):
            critique = await _visual_review(client, current)
            if critique:
                results.append("VISUAL REVIEW\n" + critique)
                review_pending = True
            reviewed = True
        if blocker == _NO_MATCHES:
            return _blocked_reply(blocker)
        if blocker:
            results.append(_blocker_note(blocker))
        if final_operation:
            return _blocked_reply(blocker) if blocker else _DONE

    raise RuntimeError("agent round budget exhausted without a final response")
