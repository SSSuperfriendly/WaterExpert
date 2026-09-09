from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


class APIBackend:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.endpoint = self.config.get(
            "endpoint",
            os.getenv("DEEPSEEK_API_ENDPOINT", "https://api.deepseek.com/chat/completions"),
        )
        self.api_key = self._resolve_api_key(self.config.get("api_key"))
        self.model = self.config.get("model", "deepseek-chat")
        self.enable_reasoning = self.config.get("enable_reasoning", True)
        self.reasoning_tokens = self.config.get("reasoning_tokens", 8000)

    def _resolve_api_key(self, configured_key: Any) -> str | None:
        if not isinstance(configured_key, str) or configured_key in {"", "YOUR_API_KEY"}:
            return os.getenv("DEEPSEEK_API_KEY")

        expanded_key = os.path.expandvars(configured_key)
        if expanded_key == configured_key and configured_key.startswith("${") and configured_key.endswith("}"):
            return os.getenv(configured_key[2:-1])

        return expanded_key or os.getenv("DEEPSEEK_API_KEY")

    def send(self, prompt: str) -> dict[str, Any]:
        """Send prompt to DeepSeek API with reasoning token capture.
        
        Args:
            prompt: The prompt string
            
        Returns:
            Response dict with content, reasoning_tokens, etc.
        """
        request_body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": int(self.config.get("max_tokens", 2048)),
        }
        
        # Add reasoning parameters for DeepSeek-V4
        if self.enable_reasoning and "deepseek" in self.model.lower():
            request_body["temperature"] = self.config.get("temperature", 0.7)
            request_body["top_p"] = self.config.get("top_p", 0.95)

        if self.api_key is None:
            return {
                "error": "API key not configured",
                "prompt": prompt,
                "reasoning_tokens": "",
            }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            
            # Extract content and reasoning from response
            result = self._extract_response(payload)
            return result
        except Exception as exc:
            return {
                "error": str(exc),
                "prompt": prompt,
                "reasoning_tokens": "",
                "content": "",
            }

    def _extract_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract content and reasoning tokens from API response.
        
        Args:
            payload: Raw API response
            
        Returns:
            Structured result dict
        """
        # Handle error response
        if "error" in payload:
            return {
                "error": payload["error"].get("message", str(payload["error"])),
                "content": "",
                "reasoning_tokens": "",
            }

        # Extract message
        try:
            message = payload["choices"][0]["message"]
            content = message.get("content", "")
            reasoning = message.get("reasoning_content", "")
        except (KeyError, IndexError):
            return {"error": "Invalid API response format", "content": "", "reasoning_tokens": ""}

        return {
            "content": content,
            "reasoning_tokens": reasoning,
            "model": payload.get("model", "deepseek-chat"),
            "usage": payload.get("usage", {}),
        }
