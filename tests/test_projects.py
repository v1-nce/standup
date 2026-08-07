from pathlib import Path

import pytest

from standup.core.projects import ChatLog, ProjectStore
from standup.errors import InvalidInput, NotFound
from tests.conftest import pdf_saying


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


def test_a_file_standup_cannot_read_is_refused(store):
    project = store.create("My App")
    with pytest.raises(InvalidInput, match="cannot read"):
        store.attach_file(project.id, "sheet.xlsx", b"a spreadsheet")


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


def test_a_document_with_no_readable_text_is_refused_and_leaves_no_copy(store):
    """It would pass the suffix check and then fail every future chat turn."""
    project = store.create("My App")
    with pytest.raises(InvalidInput, match="no readable text"):
        store.attach_file(project.id, "scan.pdf", pdf_saying(" "))

    assert store.get(project.id).resources == []
    assert not any(store.paths(project.id).context.iterdir())


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
    assert messages[0].content == "standup tomorrow"
