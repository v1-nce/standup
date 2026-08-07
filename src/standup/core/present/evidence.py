"""What a slide is allowed to cite: the files and commit messages behind each chosen item."""

from standup.core.models import Index, Selection


def evidence(selection: Selection, index: Index) -> str:
    by_sha = {commit.sha: commit for commit in index.commits}
    excerpts = {facts.path: facts.excerpt for facts in index.files if facts.excerpt}
    blocks = []
    for entry in selection.chosen:
        candidate = entry.candidate
        lines = [f"id: {candidate.id}", f"files: {', '.join(candidate.paths)}"]
        lines += [f"changed: {by_sha[sha].message}" for sha in candidate.commits if sha in by_sha]
        if candidate.id in excerpts:
            lines.append(f"text: {excerpts[candidate.id]}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
