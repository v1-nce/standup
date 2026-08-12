from datetime import UTC, datetime
from pathlib import Path

from standup.core.models import ChatMessage


class ChatLog:
    """Append-only conversation for one project."""

    def __init__(self, directory: Path) -> None:
        self._file = directory / "messages.jsonl"

    def append(self, role: str, content: str) -> ChatMessage:
        message = ChatMessage(role=role, content=content, at=datetime.now(UTC))
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with self._file.open("a", encoding="utf-8") as handle:
            handle.write(message.model_dump_json() + "\n")
        return message

    def read(self) -> list[ChatMessage]:
        if not self._file.is_file():
            return []
        lines = self._file.read_text(encoding="utf-8").splitlines()
        return [ChatMessage.model_validate_json(line) for line in lines if line.strip()]
