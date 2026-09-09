from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backends.api_backend import APIBackend
from .backends.local_backend import LocalBackend


class DeepSeekClient:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.backend_type = self.config.get("backend", "api")
        self.cache_path = Path(self.config.get("cache_path", "outputs/agents/aquaturb_gpt_traces/cache.json"))
        self.backend = self._build_backend()
        self._load_cache()

    def _build_backend(self) -> Any:
        if self.backend_type == "local":
            return LocalBackend(self.config.get("local", {}))

        api_config = self.config.get("api")
        if api_config is None:
            api_config = {
                key: value
                for key, value in self.config.items()
                if key not in {"backend", "local", "cache_path"}
            }
        return APIBackend(api_config)

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                with self.cache_path.open("r", encoding="utf-8") as fh:
                    json.load(fh)
            except Exception:
                pass

    def generate(self, prompt: str) -> dict[str, Any]:
        """Generate response with reasoning tokens.
        
        Args:
            prompt: Input prompt
            
        Returns:
            Dict with 'content', 'reasoning_tokens', 'backend', and 'prompt'
        """
        result = self.backend.send(prompt)
        
        # Normalize response structure
        return {
            "prompt": prompt,
            "content": result.get("content", ""),
            "reasoning_tokens": result.get("reasoning_tokens", ""),
            "backend": self.backend_type,
            "model": result.get("model", "unknown"),
            "error": result.get("error"),
        }

    def generate_with_fallback(self, prompt: str, fallback_response: dict[str, Any]) -> dict[str, Any]:
        """Generate with fallback to provided response if API fails.
        
        Args:
            prompt: Input prompt
            fallback_response: Fallback response if generation fails
            
        Returns:
            Generated or fallback response
        """
        result = self.generate(prompt)
        
        if result.get("error"):
            # API failed, use fallback
            return {
                "prompt": prompt,
                "content": json.dumps(fallback_response),
                "reasoning_tokens": "",
                "backend": "fallback",
                "error": None,
            }
        
        return result
