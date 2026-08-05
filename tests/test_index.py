import subprocess

import pytest

from standup.core import index
from standup.core.index.code import module_path, parse, walk
from standup.core.index.docs import emphasis
from standup.core.index.graph import aliases, edges, rank
from standup.core.index.history import commits


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


def test_walk_prunes_vendored_and_dotted_directories(repo):
    (repo / ".hidden").mkdir()
    (repo / ".hidden" / "secret.py").write_text("x = 1\n")
    walked = {p.name for p in walk(repo)}
    assert "hub.py" in walked
    assert "index.js" not in walked
    assert "secret.py" not in walked


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
    scores = emphasis(repo, parse(repo))
    assert scores["src/hub.py"] == 1.0
    assert "src/leaf.py" not in scores


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


def test_ensure_reuses_the_stored_index_until_the_tree_changes(repo, tmp_path):
    index_dir = tmp_path / "index"
    first = index.ensure(repo, index_dir)
    assert (index_dir / index.INDEX_FILE).is_file()

    assert index.ensure(repo, index_dir).built_at == first.built_at

    (repo / "src" / "new.py").write_text("def fresh():\n    pass\n")
    rebuilt = index.ensure(repo, index_dir)
    assert rebuilt.fingerprint != first.fingerprint
    assert "src/new.py" in {f.path for f in rebuilt.files}
