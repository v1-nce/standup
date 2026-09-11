from pathlib import Path

import pytest

from standup.core.index import docs
from standup.core.projects import ChatLog, ProjectStore
from standup.errors import InvalidInput, NotConfigured, NotFound
from tests.conftest import TINY_PNG, pdf_saying


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def codebase(tmp_path):
    path = tmp_path / "repo"
    (path / ".git").mkdir(parents=True)
    return path


def test_create_lays_out_a_project_with_nothing_in_it(store):
    project = store.create("My App")
    paths = store.paths(project.id)
    assert project.id.startswith("my-app-")
    assert project.resources == []
    assert (paths.root / "project.json").is_file()
    for directory in (paths.index, paths.chat, paths.deck, paths.context):
        assert directory.is_dir()


def test_two_projects_may_share_a_name(store):
    assert store.create("Standup").id != store.create("Standup").id


def test_create_without_a_name_is_refused(store):
    with pytest.raises(InvalidInput):
        store.create("   ")
    assert store.list() == []


def test_a_crash_mid_write_never_corrupts_project_json(store, monkeypatch):
    """`ProjectStore._write` used to write `project.json` directly - a crash mid-write could leave a
    reader looking at a truncated file. Same atomic write-then-rename `pipeline._put` already relies
    on for `selection.json`/`plan.json`, now shared via `_json.atomic_write`."""
    made = store.create("Original")
    good = (store.paths(made.id).root / "project.json").read_text(encoding="utf-8")

    real_replace = Path.replace

    def crash_before_replace(self, target):
        raise OSError("simulated crash")

    monkeypatch.setattr(Path, "replace", crash_before_replace)
    with pytest.raises(InvalidInput, match="could not be saved"):
        store.rename(made.id, "Renamed")

    monkeypatch.setattr(Path, "replace", real_replace)
    assert (store.paths(made.id).root / "project.json").read_text(encoding="utf-8") == good
    assert store.get(made.id).name == "Original"


def test_attaching_a_folder_records_the_path_and_copies_nothing(store, codebase):
    project = store.create("My App")
    resource = store.attach(project.id, str(codebase))

    assert resource.kind == "folder"
    assert resource.name == "repo"
    assert Path(resource.location) == codebase.resolve()
    assert store.get(project.id).resources == [resource]
    assert not any(store.paths(project.id).context.iterdir())


def test_attaching_a_file_keeps_a_copy_inside_the_project(store, codebase):
    project = store.create("My App")
    resource = store.attach_file(project.id, "notes.md", b"# Notes")

    kept = Path(resource.location)
    assert resource.kind == "file"
    assert kept.read_bytes() == b"# Notes"
    assert kept.parent == store.paths(project.id).context / resource.id


def test_a_read_failure_while_attaching_a_lone_file_by_path_is_refused(store, tmp_path, monkeypatch):
    project = store.create("My App")
    doc = tmp_path / "notes.md"
    doc.write_text("# Notes")

    def boom(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", boom)
    with pytest.raises(InvalidInput, match="could not be read"):
        store.attach_path(project.id, str(doc))


def test_a_resolve_failure_while_attaching_a_folder_is_refused(store, monkeypatch):
    project = store.create("My App")

    def boom(self):
        raise OSError("too many levels of symbolic links")

    monkeypatch.setattr(Path, "resolve", boom)
    with pytest.raises(InvalidInput, match="could not be resolved"):
        store.attach(project.id, "somewhere")


def test_a_file_standup_cannot_read_is_refused(store):
    project = store.create("My App")
    with pytest.raises(InvalidInput, match="cannot read"):
        store.attach_file(project.id, "book.epub", b"an ebook")


def test_a_folder_inside_an_attached_folder_is_refused(store, codebase):
    """The same file would arrive twice, as two candidates nothing downstream can tell apart."""
    project = store.create("My App")
    inner = codebase / "src"
    inner.mkdir()
    store.attach(project.id, str(codebase))

    with pytest.raises(InvalidInput, match="already covers"):
        store.attach(project.id, str(inner))
    with pytest.raises(InvalidInput, match="already covers"):
        store.attach(project.id, str(codebase))


def test_two_documents_may_share_a_name(store):
    """Every repository has a README.md. Only re-uploading the identical file is the accident."""
    project = store.create("My App")
    first = store.attach_file(project.id, "README.md", b"# Standup")
    second = store.attach_file(project.id, "README.md", b"# Forge")

    assert first.id != second.id
    assert [r.name for r in store.get(project.id).resources] == ["README.md", "README.md"]


def test_the_identical_document_is_not_attached_twice(store):
    project = store.create("My App")
    store.attach_file(project.id, "notes.md", b"# Notes")
    with pytest.raises(InvalidInput, match="already attached"):
        store.attach_file(project.id, "notes.md", b"# Notes")


def test_a_write_failure_while_attaching_is_refused_and_leaves_no_copy(store, monkeypatch):
    project = store.create("My App")

    def boom(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", boom)
    with pytest.raises(InvalidInput, match="could not be saved"):
        store.attach_file(project.id, "notes.md", b"# Notes")

    assert store.get(project.id).resources == []
    assert not any(store.paths(project.id).context.iterdir())


def test_a_document_with_no_readable_text_is_refused_and_leaves_no_copy(store):
    """It would pass the suffix check and then fail every future chat turn."""
    project = store.create("My App")
    with pytest.raises(InvalidInput, match="no readable text"):
        store.attach_file(project.id, "scan.pdf", pdf_saying(" "))

    assert store.get(project.id).resources == []
    assert not any(store.paths(project.id).context.iterdir())


def test_attaching_an_image_without_a_model_is_kept(store, monkeypatch):
    """An image is a resource even when no model can describe it; only an unreadable file fails."""
    monkeypatch.setattr(docs, "_DESCRIBED", {})

    def unconfigured(data, media_type, *, prompt):
        raise NotConfigured("no key")

    monkeypatch.setattr(docs, "describe_image_sync", unconfigured)
    project = store.create("Images")

    resource = store.attach_file(project.id, "photo.png", TINY_PNG)

    assert resource.kind == "file"
    assert store.get(project.id).resources == [resource]


def test_detaching_takes_the_copy_and_the_derived_facts_with_it(store):
    project = store.create("My App")
    resource = store.attach_file(project.id, "notes.md", b"# Notes")
    derived = store.paths(project.id).index / resource.id
    derived.mkdir(parents=True)
    (derived / "facts.json").write_text("{}")

    store.detach(project.id, resource.id)

    assert store.get(project.id).resources == []
    assert not (store.paths(project.id).context / resource.id).exists()
    assert not derived.exists()


def test_detaching_something_that_was_never_attached_is_not_found(store):
    project = store.create("My App")
    with pytest.raises(NotFound):
        store.detach(project.id, "nope")


def test_attaching_a_missing_directory_is_refused(store, tmp_path):
    project = store.create("Ghost")
    with pytest.raises(InvalidInput, match="is not a directory"):
        store.attach(project.id, str(tmp_path / "nope"))
    assert store.get(project.id).resources == []


def test_list_and_get_and_delete(store):
    first = store.create("First")
    second = store.create("Second")

    assert {p.id for p in store.list()} == {first.id, second.id}
    assert store.get(first.id).name == "First"

    store.delete(first.id)
    assert {p.id for p in store.list()} == {second.id}
    with pytest.raises(NotFound):
        store.get(first.id)


def test_chat_round_trips(tmp_path):
    log = ChatLog(tmp_path / "chat")
    assert log.read() == []
    log.append("user", "standup tomorrow")
    log.append("assistant", "on it")
    messages = log.read()
    assert [m.role for m in messages] == ["user", "assistant"]


def test_a_corrupt_project_file_is_a_clean_error_not_a_crash(store):
    made = store.create("Demo")
    (store.paths(made.id).root / "project.json").write_text("not json", encoding="utf-8")

    with pytest.raises(InvalidInput, match="corrupt"):
        store.get(made.id)


def test_a_corrupt_chat_line_is_a_clean_error_not_a_crash(tmp_path):
    log = ChatLog(tmp_path / "chat")
    log.append("user", "standup tomorrow")
    (tmp_path / "chat" / "messages.jsonl").open("a", encoding="utf-8").write("not json\n")

    with pytest.raises(InvalidInput, match="corrupt"):
        log.read()
