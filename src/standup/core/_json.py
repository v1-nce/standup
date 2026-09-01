"""One place to turn a stored file into a model, or a clean error - not a crash the caller can't
catch - and one place to write one back durably. Shared by every module that keeps its own JSON on
disk."""

from pathlib import Path

from pydantic import BaseModel, ValidationError

from standup.errors import InvalidInput


def load_json[Model: BaseModel](model: type[Model], text: str, what: str) -> Model:
    try:
        return model.model_validate_json(text)
    except ValidationError as failure:
        raise InvalidInput(f"{what} is corrupt: {failure}") from failure


def atomic_write(path: Path, text: str) -> None:
    """Write-then-rename: a crash mid-write leaves the `.tmp` truncated, never the file a reader
    opens. `Path.replace` is atomic on both POSIX and Windows for a same-volume rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
