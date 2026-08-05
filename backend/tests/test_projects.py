import pytest

from errors import InvalidInput, NotFound
from projects import ChatLog, ProjectStore


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def codebase(tmp_path):
    path = tmp_path / "repo"
    (path / ".git").mkdir(parents=True)
    return path


def test_create_lays_out_the_project(store, codebase):
    project = store.create("My App", str(codebase))
    paths = store.paths(project.id)
    assert project.id.startswith("my-app-")
    assert project.source.kind == "local"
    assert project.source.has_git is True
    assert (paths.root / "project.json").is_file()
    for directory in (paths.index, paths.chat, paths.decks, paths.cache):
        assert directory.is_dir()


def test_local_source_is_not_copied(store, codebase):
    project = store.create("My App", str(codebase))
    assert store.working_tree(project.id) == codebase.resolve()
    assert not store.paths(project.id).clone.exists()


def test_non_git_directory_is_recorded_not_rejected(store, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert store.create("Plain", str(plain)).source.has_git is False


def test_same_source_cannot_register_twice(store, codebase):
    store.create("My App", str(codebase))
    with pytest.raises(InvalidInput):
        store.create("My App", str(codebase))


def test_missing_directory_leaves_nothing_behind(store, tmp_path):
    with pytest.raises(InvalidInput):
        store.create("Ghost", str(tmp_path / "nope"))
    assert store.list() == []


def test_list_and_get_and_delete(store, codebase, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    first = store.create("First", str(codebase))
    second = store.create("Second", str(other))

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
