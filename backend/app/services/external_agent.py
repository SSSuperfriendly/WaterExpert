from __future__ import annotations

"""Client for the externally deployed WaterExpert agent API.

The self-developed model stack (MSCIM / CMFBE / KnowledgeBase / AquaTurbGPT /
RL-TGRR / Safety) is hosted by the collaborator at ``/api`` and speaks the
REST contract in ``docs/internal/INTEGRATION_GUIDE.md``:

- ``GET  /health``          — per-agent readiness
- ``GET  /scenarios``       — supported governance scenarios
- ``POST /strategy``        — queue a strategy-generation job (async)
- ``GET  /strategy/{id}``   — poll a queued job

This service is the single hop between the platform and that deployment. It is
deliberately thin: it validates nothing about the model itself, forwards the
request/response bodies, and maps connectivity/protocol failures onto one
``AgentUnavailable`` refusal the API layer turns into a 502.
"""

from typing import Any

import httpx

#: Base URL used when ``WATEREXPERT_AGENT_API_URL`` is not set. Kept here so the
#: module has one default even outside the FastAPI settings object.
DEFAULT_AGENT_API_URL = "http://219.228.144.101:8000/api"


class AgentUnavailable(Exception):
    """The deployed WaterExpert agent API could not be reached or misbehaved.

    ``message`` is for operators/logs; the API layer raises a 502 with the
    stable ``agent_unavailable`` code for the frontend to localize.
    """


class ExternalAgentService:
    """Thin async proxy over the deployed WaterExpert agent API."""

    def __init__(
        self,
        base_url: str = DEFAULT_AGENT_API_URL,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") or DEFAULT_AGENT_API_URL
        self.timeout_seconds = timeout_seconds
        #: Injectable only for tests; production always uses the real network.
        self._transport = transport

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds), transport=self._transport
            ) as client:
                response = await client.request(method, url, json=json)
        except httpx.HTTPError as exc:
            raise AgentUnavailable(
                f"WaterExpert agent API unreachable at {self.base_url}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            raise AgentUnavailable(
                f"WaterExpert agent API returned non-JSON at {path} "
                f"(HTTP {response.status_code})."
            ) from None

        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise AgentUnavailable(
                f"WaterExpert agent API error {response.status_code} at {path}: "
                f"{detail if detail is not None else payload}"
            )
        return payload

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def scenarios(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/scenarios")

    async def create_strategy(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Queue a strategy-generation job and return ``{"job_id": ...}``."""
        return await self._request("POST", "/strategy", json=payload)

    async def strategy(self, job_id: str) -> dict[str, Any]:
        """Poll a queued strategy job by id."""
        return await self._request("GET", f"/strategy/{job_id}")
