from __future__ import annotations

from typing import Any


class MessageBus:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def consume(self) -> list[dict[str, Any]]:
        items = self.messages.copy()
        self.messages.clear()
        return items
