"""What a slide is allowed to cite: the files behind each chosen item, and what they actually say."""

from standup.core.models import Index, Selection


def evidence(selection: Selection, index: Index, sources: dict[str, str] | None = None) -> str:
    """Everything the model may write a slide from.

    `sources` is the current text of each file, read from disk by the caller — the index stores none,
    because storing it would grow with the resource. Without it a slide can only restate a commit
    message, which is what the deck used to read like.
    """
    by_sha = {commit.sha: commit for commit in index.commits}
    excerpts = {facts.path: facts.excerpt for facts in index.files if facts.excerpt}
    defined = {facts.path: facts.symbols for facts in index.files}
    said = sources or {}

    blocks = []
    for entry in selection.chosen:
        candidate = entry.candidate
        lines = [f"id: {candidate.id}", f"files: {', '.join(candidate.paths)}"]

        # Named here because `slide_problems` rejects any call this list doesn't cover, and the model
        # cannot honour a vocabulary it was never shown.
        names = dict.fromkeys(
            symbol.name for path in candidate.paths for symbol in defined.get(path, [])
        )
        if names:
            lines.append(f"defines: {', '.join(names)}")

        lines += [f"changed: {by_sha[sha].message}" for sha in candidate.commits if sha in by_sha]

        # By path, not by id: a candidate covering several files keeps its text either way.
        text = next((excerpts[path] for path in candidate.paths if path in excerpts), "")
        if text:
            lines.append(f"text: {text}")

        source = next((said[path] for path in candidate.paths if path in said), "")
        if source:
            lines.append(f"source:\n{source}")

        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
