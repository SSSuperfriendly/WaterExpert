from __future__ import annotations

from typing import Any


class LocalBackend:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.model_path = self.config.get("model_path", "local_deepseek_model")

    def send(self, prompt: str) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "prompt": prompt,
            "response": "[local backend placeholder] DeepSeek-V4 本地模式当前为占位实现。",
        }
