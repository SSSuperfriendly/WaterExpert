from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentMessage:
    sender: str
    payload: dict[str, Any]
    metadata: dict[str, Any] | None = None


class BaseAgent(ABC):
    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        self.name = name
        self.config = config or {}

    @abstractmethod
    def act(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "type": type(self).__name__, "config": self.config}
