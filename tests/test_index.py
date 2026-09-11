import subprocess
from datetime import UTC, datetime

import pytest

from standup.core import index
from standup.core.index import docs
from standup.core.index.code import module_path, parse, walk
from standup.core.index.docs import emphasis, prose, read, readable
from standup.core.index.graph import aliases, edges, rank
from standup.core.index.history import commits
from standup.core.models import Facts, FileFacts, Symbol
from standup.errors import InvalidInput, NotConfigured
from tests.conftest import TINY_PNG, docx_saying, pdf_saying, pptx_saying, xlsx_saying


@pytest.fixture
def repo(tmp_path):
    """A tiny project: two callers, one hub, one leaf, plus junk that must never be indexed."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "src" / "hub.py").write_text("class Router:\n    def dispatch(self):\n        pass\n")
    (root / "src" / "caller_a.py").write_text("from hub import Router\n\ndef a():\n    Router()\n")
    (root / "src" / "caller_b.py").write_text("import hub\n\ndef b():\n    hub.Router()\n")
    (root / "src" / "leaf.py").write_text("def unused():\n    pass\n")
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1\n")
    (root / "README.md").write_text("The Router is the heart of this project. Router, Router.\n")
    return root


def test_walk_prunes_vendored_and_dotted_names(repo):
    (repo / ".hidden").mkdir()
    (repo / ".hidden" / "secret.py").write_text("x = 1\n")
    (repo / ".env").write_text("API_KEY=sk-real-secret\n")

    walked = {p.name for p in walk(repo)}
    assert "hub.py" in walked
    assert "index.js" not in walked
    assert "secret.py" not in walked
    # A repository's own credentials are a file tree-sitter parses happily. Never indexed.
    assert ".env" not in walked


def test_walk_prunes_test_and_example_directories(repo):
    (repo / "src" / "tests").mkdir(parents=True)
    (repo / "src" / "tests" / "test_hub.py").write_text("def test_x():\n    pass\n")
    (repo / "spec" / "unit").mkdir(parents=True)
    (repo / "spec" / "unit" / "hub_spec.py").write_text("def test_x():\n    pass\n")
    (repo / "examples" / "demo").mkdir(parents=True)
    (repo / "examples" / "demo" / "run.py").write_text("print('demo')\n")

    walked = {p.relative_to(repo).as_posix() for p in walk(repo)}
    assert "src/tests/test_hub.py" not in walked
    assert "spec/unit/hub_spec.py" not in walked
    assert "examples/demo/run.py" not in walked


def test_parse_extracts_symbols_and_import_tokens(repo):
    facts = {f.path: f for f in parse(repo)}
    hub = facts["src/hub.py"]
    assert {s.name for s in hub.symbols} == {"Router", "dispatch"}
    assert hub.symbols[0].line == 1
    assert "hub" in facts["src/caller_a.py"].imports
    assert "hub" in facts["src/caller_b.py"].imports


def test_rank_puts_the_depended_on_file_above_the_leaf(repo):
    ranked = rank(parse(repo))
    assert ranked["src/hub.py"] > ranked["src/leaf.py"]
    assert sum(ranked.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("from models import Project", "models"),
        ("from index.code import walk", "index/code"),
        ("import os.path", "os/path"),
        ("from . import sibling", "."),
        ("from ..pkg.deep import thing", "..pkg/deep"),
        ("import Button from './components/Button'", ".components/Button"),
        ("import {parse} from './util.js'", ".util"),
        ("import {a, b} from '../lib/util'", "..lib/util"),
        ('"github.com/me/proj/internal/store"', "github.com/me/proj/internal/store"),
        ("use crate::index::graph::rank;", "crate/index/graph/rank"),
        ("import com.example.app.Router;", "com/example/app/Router"),
    ],
)
def test_module_path_keeps_the_module_and_drops_the_symbols(statement, expected):
    assert module_path(statement) == expected


def test_importing_a_symbol_does_not_credit_a_file_named_after_it(repo):
    (repo / "src" / "router.py").write_text("def helper():\n    pass\n")
    (repo / "src" / "app.py").write_text("from hub import Router\n")
    linked = edges(parse(repo))
    assert linked["src/app.py"] == {"src/hub.py"}


def test_a_submodule_import_credits_the_submodule_not_the_package(repo):
    package = repo / "src" / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "deep.py").write_text("def thing():\n    pass\n")
    (repo / "src" / "app.py").write_text("from pkg.deep import thing\n")
    linked = edges(parse(repo))
    assert linked["src/app.py"] == {"src/pkg/deep.py"}


def test_a_relative_import_resolves_inside_the_importer_s_own_directory(repo):
    nested = repo / "src" / "nested"
    nested.mkdir()
    (nested / "hub.py").write_text("class Local:\n    pass\n")
    (nested / "user.ts").write_text("import {Local} from './hub'\n")
    linked = edges(parse(repo))
    assert linked["src/nested/user.ts"] == {"src/nested/hub.py"}


def test_an_absolute_import_resolves_from_the_source_root_not_by_name(repo):
    """`from hub import ...` means src/hub.py, not the same-named file beside a caller."""
    (repo / "src" / "api").mkdir()
    (repo / "src" / "api" / "hub.py").write_text("class Wrong:\n    pass\n")
    (repo / "src" / "api" / "user.py").write_text("from hub import Router\n")
    linked = edges(parse(repo))
    assert linked["src/api/user.py"] == {"src/hub.py"}


def test_an_external_module_never_decays_into_a_bare_filename(repo):
    (repo / "src" / "wsgi.py").write_text("app = None\n")
    (repo / "src" / "app.py").write_text("from _typeshed.wsgi import StartResponse\n")
    linked = edges(parse(repo))
    assert linked["src/app.py"] == set()


def test_a_vendored_module_path_matches_on_its_tail(repo):
    store = repo / "internal" / "store"
    store.mkdir(parents=True)
    (store / "store.go").write_text("package store\n\nfunc Open() {}\n")
    (repo / "main.go").write_text('package main\n\nimport "github.com/me/proj/internal/store"\n')
    linked = edges(parse(repo))
    assert linked["main.go"] == {"internal/store/store.go"}


def test_a_buried_namesake_does_not_steal_the_real_module_s_rank(repo):
    fixture = repo / "src" / "fixtures" / "deep" / "hub.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("class Decoy:\n    pass\n")
    ranked = rank(parse(repo))
    assert ranked["src/hub.py"] > ranked["src/fixtures/deep/hub.py"]


def test_a_config_file_never_absorbs_rank_from_a_package_of_the_same_name(repo):
    (repo / "hub.toml").write_text("[tool]\nname = 'hub'\n")
    ranked = rank(parse(repo))
    assert ranked["hub.toml"] < ranked["src/hub.py"]


def test_emphasis_follows_what_the_project_writes_about(repo):
    scores = emphasis(prose(repo), parse(repo))
    assert scores["src/hub.py"] == 1.0
    assert "src/leaf.py" not in scores


def test_emphasis_credits_ruby_style_predicate_and_bang_identifiers():
    """A bare \\w+ tally would drop the ? off "valid?", scoring it as never mentioned."""
    facts = [
        FileFacts(path="lib/user.rb", content_hash="h", symbols=[Symbol(name="valid?", kind="Method", line=1)])
    ]
    text = "The valid? method checks the record. See valid? again."
    assert emphasis(text, facts)["lib/user.rb"] == 1.0


def test_emphasis_credits_cpp_operator_overload_identifiers():
    """No fixed character class enumerates every language's punctuation — operator+ needs the
    same whole-name credit valid? gets, without special-casing + into the tokenizer."""
    facts = [
        FileFacts(
            path="src/vector.cpp", content_hash="h", symbols=[Symbol(name="operator+", kind="Function", line=1)]
        )
    ]
    text = "The operator+ overload adds two vectors. See operator+ for the implementation."
    assert emphasis(text, facts)["src/vector.cpp"] == 1.0


def test_emphasis_credits_a_symbol_mention_regardless_of_case():
    """Filename mentions were already case-insensitive; a symbol mentioned as "the Router class"
    used to score 0 for a symbol literally named "Router" if prose ever lowercased it, or vice
    versa - the same inconsistency this fixes for filenames stays fixed for symbols too."""
    facts = [FileFacts(path="src/hub.py", content_hash="h", symbols=[Symbol(name="Router", kind="Class", line=1)])]
    text = "Sets up the router. See Router for the implementation."
    assert emphasis(text, facts)["src/hub.py"] == 1.0


def test_merged_caps_the_joined_prose_across_resources(monkeypatch):
    """Each resource's own text is already capped individually; the join across resources must
    not let a project with several large resources hand emphasis() an uncapped string."""
    monkeypatch.setattr(index, "MAX_DOC_CHARS", 10)
    seen = {}

    def spy(text, files):
        seen["text"] = text
        return {}

    monkeypatch.setattr(index, "emphasis", spy)

    now = datetime.now(UTC)
    parts = [
        ("a", Facts(fingerprint="a", built_at=now, text="A" * 10)),
        ("b", Facts(fingerprint="b", built_at=now, text="B" * 10)),
    ]
    index.merged(parts)

    assert len(seen["text"]) <= 10


def test_no_git_means_no_commits_not_a_failure(repo):
    assert commits(repo) == ([], True)


def test_commits_read_the_real_history(repo):
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "Tester"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "first commit"],
    ):
        subprocess.run([*command[:1], "-C", str(repo), *command[1:]], check=True, capture_output=True)

    history, complete = commits(repo)
    assert complete
    assert len(history) == 1
    assert history[0].message == "first commit"
    assert history[0].author == "Tester"
    assert history[0].changes["src/hub.py"] > 0
    assert history[0].changes["src/leaf.py"] < history[0].changes["src/caller_a.py"]


def test_a_rename_credits_churn_to_the_file_as_it_exists_today(repo):
    """`git log --numstat` renders a rename as `prefix{old => new}suffix` (or bare `old => new` with
    no shared affix) - unresolved, that whole expression read as one fabricated path, so the real
    file lost its churn credit and a candidate for a path that never existed appeared instead."""
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "Tester"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "first commit"],
        ["git", "mv", "src/hub.py", "src/core.py"],
        ["git", "commit", "-qm", "reorganise"],
    ):
        subprocess.run([*command[:1], "-C", str(repo), *command[1:]], check=True, capture_output=True)

    history, _ = commits(repo)
    rename = next(c for c in history if c.message == "reorganise")
    assert set(rename.changes) == {"src/core.py"}
    assert not any("=>" in path or "{" in path for commit in history for path in commit.changes)


def test_a_capped_history_says_so_rather_than_pretending_to_be_whole(repo):
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "Tester"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "first"],
        ["git", "commit", "-qm", "second", "--allow-empty"],
    ):
        subprocess.run(
            [*command[:1], "-C", str(repo), *command[1:]], check=True, capture_output=True
        )

    assert commits(repo)[1] is True
    capped, complete = commits(repo, limit=1)
    assert len(capped) == 1
    assert complete is False


def test_a_package_manifest_names_the_directory_it_stands_for(repo):
    package = repo / "packages" / "widget"
    (package / "src").mkdir(parents=True)
    (package / "package.json").write_text('{"name": "@acme/widget"}')
    (package / "src" / "index.ts").write_text("export const a = 1\n")
    (repo / "src" / "user.ts").write_text("import {a} from '@acme/widget'\n")

    files = parse(repo)
    assert aliases(repo) == {"@acme/widget": "packages/widget/src"}
    assert edges(files, aliases(repo))["src/user.ts"] == {"packages/widget/src/index.ts"}


def test_merging_carries_every_path_home_to_its_resource(repo, tmp_path):
    note = tmp_path / "notes.md"
    note.write_text("The Router is the point of all this.\n")

    whole = index.merged([("app", index.build(repo)), ("notes", index.build(note))])
    paths = {facts.path for facts in whole.files}

    assert "app/src/hub.py" in paths
    assert "notes/notes.md" in paths
    # The document's words are evidence, so they travel with it and reach the model.
    assert "Router" in next(f.excerpt for f in whole.files if f.path == "notes/notes.md")


def test_a_small_resource_cannot_flatten_a_large_one(repo, tmp_path):
    """Rank is relative. Computed per resource and merged, a lone file would score ~1.0 and
    every file in the real repository would collapse to nothing."""
    note = tmp_path / "notes.md"
    note.write_text("hello\n")

    whole = index.merged([("app", index.build(repo)), ("notes", index.build(note))])

    assert whole.rank["app/src/hub.py"] > whole.rank["app/src/leaf.py"]
    assert whole.rank["app/src/hub.py"] > whole.rank.get("notes/notes.md", 0.0)


def test_an_attached_document_lifts_what_it_writes_about(repo, tmp_path):
    note = tmp_path / "notes.md"
    note.write_text("Router, Router, Router. The dispatch path is the whole story.\n")

    alone = index.merged([("app", index.build(repo))])
    with_note = index.merged([("app", index.build(repo)), ("notes", index.build(note))])

    assert with_note.emphasis["app/src/hub.py"] > alone.emphasis.get("app/src/leaf.py", 0.0)
    assert "app/src/hub.py" in with_note.emphasis


def test_a_lone_file_is_named_by_itself_and_read_for_its_text(tmp_path):
    note = tmp_path / "notes.md"
    note.write_text("# Standup\n\nWhat the meeting is for.\n")

    facts = index.build(note)
    assert [f.path for f in facts.files] == ["notes.md"]
    assert "What the meeting is for" in facts.text


def test_a_file_with_no_readable_text_is_refused_rather_than_attached_empty(tmp_path):
    blank = tmp_path / "empty.md"
    blank.write_text("   \n")
    with pytest.raises(InvalidInput, match="no readable text"):
        index.build(blank)


def test_readable_covers_documents_source_and_office_formats_but_not_an_ebook():
    assert readable("spec.pdf")
    assert readable("notes.md")
    assert readable("main.py")
    assert readable("sheet.xlsx")
    assert readable("deck.pptx")
    assert readable("brief.docx")
    assert readable("photo.png")
    assert not readable("book.epub")


def test_a_pdf_is_read_as_text(tmp_path):
    document = tmp_path / "spec.pdf"
    document.write_bytes(pdf_saying("Standup selects what matters"))
    assert "Standup selects what matters" in read(document)


def test_a_spreadsheet_is_read_cell_by_cell(tmp_path):
    document = tmp_path / "sheet.xlsx"
    document.write_bytes(xlsx_saying("Q3 revenue is up"))
    assert "Q3 revenue is up" in read(document)


def test_a_slide_deck_is_read_text_frame_by_text_frame(tmp_path):
    document = tmp_path / "deck.pptx"
    document.write_bytes(pptx_saying("The migration finished Tuesday"))
    assert "The migration finished Tuesday" in read(document)


def test_a_word_document_is_read_paragraph_by_paragraph(tmp_path):
    document = tmp_path / "brief.docx"
    document.write_bytes(docx_saying("Rollout is blocked on the auth change"))
    assert "Rollout is blocked on the auth change" in read(document)


@pytest.mark.parametrize("suffix", [".xlsx", ".pptx", ".docx"])
def test_a_corrupt_office_document_is_refused_rather_than_crashing(tmp_path, suffix):
    document = tmp_path / f"broken{suffix}"
    document.write_bytes(b"not a real office document")
    with pytest.raises(InvalidInput, match="could not be read"):
        read(document)


def test_an_undecodable_source_file_is_refused_rather_than_silently_empty(tmp_path):
    document = tmp_path / "notes.txt"
    document.write_bytes(b"\xff\xfe not valid utf-8")
    with pytest.raises(InvalidInput, match="could not be read"):
        read(document)


def test_prose_skips_an_unreadable_doc_file_rather_than_failing_the_whole_walk(repo):
    (repo / "BROKEN.txt").write_bytes(b"\xff\xfe not valid utf-8")
    assert "Router" in prose(repo)


def test_an_image_is_described_by_the_configured_model(tmp_path, monkeypatch):
    monkeypatch.setattr(docs, "_DESCRIBED", {})
    seen = {}

    def fake(data, media_type, *, prompt):
        seen["data"], seen["media_type"], seen["prompt"] = data, media_type, prompt
        return "A dashboard showing 3 failing tests."

    monkeypatch.setattr(docs, "describe_image_sync", fake)
    photo = tmp_path / "photo.png"
    photo.write_bytes(TINY_PNG)

    assert read(photo) == "A dashboard showing 3 failing tests."
    assert seen["data"] == TINY_PNG
    assert seen["media_type"] == "image/png"


def test_describing_the_same_image_twice_calls_the_model_once(tmp_path, monkeypatch):
    """Attach-time validation and index-time extraction both read() the file the model call
    is the one expensive step, and it must not be billed twice for one attach."""
    monkeypatch.setattr(docs, "_DESCRIBED", {})
    calls = []

    def fake(data, media_type, *, prompt):
        calls.append(data)
        return "A whiteboard sketch of the auth flow."

    monkeypatch.setattr(docs, "describe_image_sync", fake)
    photo = tmp_path / "photo.png"
    photo.write_bytes(TINY_PNG)

    assert read(photo) == read(photo)
    assert len(calls) == 1


def test_an_image_with_no_model_configured_is_read_without_text(tmp_path, monkeypatch):
    """No model (or a model that cannot see images) leaves the image undescribed, not unreadable."""
    monkeypatch.setattr(docs, "_DESCRIBED", {})

    def unconfigured(data, media_type, *, prompt):
        raise NotConfigured("No model key. Set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env")

    monkeypatch.setattr(docs, "describe_image_sync", unconfigured)
    photo = tmp_path / "photo.png"
    photo.write_bytes(TINY_PNG)

    assert read(photo) == ""


def test_a_lone_image_with_no_description_is_still_indexed(tmp_path, monkeypatch):
    """A lone image whose description failed is a valid resource, not a 'no readable text' failure."""
    monkeypatch.setattr(docs, "_DESCRIBED", {})

    def unconfigured(data, media_type, *, prompt):
        raise NotConfigured("no key")

    monkeypatch.setattr(docs, "describe_image_sync", unconfigured)
    photo = tmp_path / "photo.png"
    photo.write_bytes(TINY_PNG)

    facts = index.build(photo)
    assert [f.path for f in facts.files] == ["photo.png"]
    assert facts.text == ""


def test_ensure_reuses_the_stored_facts_until_the_resource_changes(repo, tmp_path):
    facts_dir = tmp_path / "index"
    first = index.ensure(repo, facts_dir)
    assert (facts_dir / index.FACTS_FILE).is_file()

    assert index.ensure(repo, facts_dir).built_at == first.built_at

    (repo / "src" / "new.py").write_text("def fresh():\n    pass\n")
    rebuilt = index.ensure(repo, facts_dir)
    assert rebuilt.fingerprint != first.fingerprint
    assert "src/new.py" in {f.path for f in rebuilt.files}


def test_a_corrupt_facts_cache_self_heals_by_rebuilding(repo, tmp_path):
    """The source it was derived from is still right there, so unlike a corrupt selection or plan
    (irreplaceable state), a bad cache file costs a rebuild, not an error the caller has to handle."""
    facts_dir = tmp_path / "index"
    index.ensure(repo, facts_dir)
    (facts_dir / index.FACTS_FILE).write_text("not json", encoding="utf-8")

    rebuilt = index.ensure(repo, facts_dir)
    assert "src/hub.py" in {f.path for f in rebuilt.files}
