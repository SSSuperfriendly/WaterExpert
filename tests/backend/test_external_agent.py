from __future__ import annotations

import asyncio
import json
import unittest

import httpx
from pydantic import ValidationError

from backend.app.schemas import AgentExplainRequest, AgentStrategyRequest
from backend.app.services.external_agent import AgentUnavailable, ExternalAgentService


def _handler(payload: dict | list, *, status: int = 200) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


class ExternalAgentServiceTest(unittest.IsolatedAsyncioTestCase):
    """The bridge forwards the documented agent-API contract 1:1 and maps
    connectivity/protocol failures onto one ``AgentUnavailable`` refusal."""

    def _service(self, transport: httpx.MockTransport) -> ExternalAgentService:
        return ExternalAgentService(
            base_url="http://agent.test/api", timeout_seconds=5.0, transport=transport
        )

    async def test_health_proxies_agent_statuses(self) -> None:
        payload = {"status": "healthy", "agents": {"MSCIM": "ready", "RL-TGRR": "ready"}}
        service = self._service(_handler(payload))

        result = await service.health()

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["agents"]["MSCIM"], "ready")

    async def test_scenarios_returns_list(self) -> None:
        payload = [{"code": "S1", "name": "External Input Type"}]
        service = self._service(_handler(payload))

        result = await service.scenarios()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["code"], "S1")

    async def test_create_strategy_returns_job_id(self) -> None:
        payload = {"job_id": "job-1", "status": "queued"}
        service = self._service(_handler(payload))

        result = await service.create_strategy({"scenario": "s1_external_input", "state": {}})

        self.assertEqual(result["job_id"], "job-1")

    async def test_strategy_status_returns_completed_payload(self) -> None:
        payload = {"job_id": "job-1", "status": "completed", "strategy": {"release_rate": 8.5}}
        service = self._service(_handler(payload))

        result = await service.strategy("job-1")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["strategy"]["release_rate"], 8.5)

    async def test_explain_proxies_narrative(self) -> None:
        sent: dict = {}
        explain_payload = {
            "scenario": "s1_external_input",
            "state": {"date": "2025-10-31", "turbidity": 25.5, "flow_rate": 28.5},
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            sent["url"] = str(request.url)
            sent["method"] = request.method
            sent["body"] = json.loads(request.content.decode())
            return httpx.Response(
                200,
                json={
                    "scenario": "s1_external_input",
                    "explanation": "场景诊断……",
                    "matched_cases": [{"id": "case_002", "similarity": 0.904}],
                },
            )

        service = self._service(httpx.MockTransport(handler))
        result = await service.explain(explain_payload)

        self.assertEqual(sent["method"], "POST")
        self.assertTrue(sent["url"].endswith("/api/explain"))
        self.assertEqual(sent["body"], explain_payload)
        self.assertTrue(result["explanation"])
        self.assertEqual(result["matched_cases"][0]["similarity"], 0.904)

    async def test_http_error_becomes_agent_unavailable(self) -> None:
        service = self._service(_handler({"detail": "boom"}, status=500))

        with self.assertRaises(AgentUnavailable):
            await service.health()

    async def test_non_json_body_becomes_agent_unavailable(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>not json</html>")

        service = self._service(httpx.MockTransport(handler))

        with self.assertRaises(AgentUnavailable):
            await service.health()

    async def test_network_error_becomes_agent_unavailable(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        service = self._service(httpx.MockTransport(handler))

        with self.assertRaises(AgentUnavailable):
            await service.health()


class AgentStrategyRequestSchemaTest(unittest.TestCase):
    def test_accepts_the_documented_example(self) -> None:
        payload = {
            "scenario": "s1_external_input",
            "state": {
                "date": "2025-10-31",
                "turbidity": 25.5,
                "flow_rate": 28.5,
                "temperature": 18.2,
                "ph": 7.5,
                "dissolved_oxygen": 8.3,
                "chlorophyll_a": 5.2,
                "rainfall_3d": 45.3,
                "rainfall_7d": 120.5,
            },
            "episodes": 1,
            "backend": "api",
        }
        request = AgentStrategyRequest.model_validate(payload)

        self.assertEqual(request.scenario, "s1_external_input")
        self.assertEqual(request.state.turbidity, 25.5)
        self.assertEqual(request.episodes, 1)

    def test_requires_turbidity_and_flow_rate(self) -> None:
        payload = {"scenario": "s1_external_input", "state": {"date": "2025-10-31"}}
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(payload)

    def test_rejects_negative_turbidity(self) -> None:
        payload = {
            "scenario": "s1_external_input",
            "state": {"date": "2025-10-31", "turbidity": -1, "flow_rate": 10},
        }
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(payload)

    def test_rejects_bad_date_format(self) -> None:
        payload = {
            "scenario": "s1_external_input",
            "state": {"date": "31/10/2025", "turbidity": 20, "flow_rate": 10},
        }
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(payload)

    def test_episodes_capped_at_ten(self) -> None:
        payload = {
            "scenario": "s1_external_input",
            "state": {"date": "2025-10-31", "turbidity": 20, "flow_rate": 10},
            "episodes": 11,
        }
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(payload)

    #: State bounds mirror the deployed WaterQualityState (live /openapi.json):
    #: turbidity <=500, flow_rate <=100, temperature 0-50, DO <=15, chl-a <=100.
    #: Tight bounds fail fast at our API instead of as an opaque 502 upstream.
    def _state(self, **overrides: float) -> dict:
        base = {"date": "2025-10-31", "turbidity": 25.5, "flow_rate": 28.5}
        base.update(overrides)
        return base

    def test_rejects_turbidity_above_500(self) -> None:
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(
                {"scenario": "s1_external_input", "state": self._state(turbidity=501)}
            )

    def test_rejects_flow_rate_above_100(self) -> None:
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(
                {"scenario": "s1_external_input", "state": self._state(flow_rate=101)}
            )

    def test_rejects_temperature_outside_0_50(self) -> None:
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(
                {"scenario": "s1_external_input", "state": self._state(temperature=51)}
            )

    def test_rejects_dissolved_oxygen_above_15(self) -> None:
        with self.assertRaises(ValidationError):
            AgentStrategyRequest.model_validate(
                {"scenario": "s1_external_input", "state": self._state(dissolved_oxygen=16)}
            )

    def test_accepts_boundary_values(self) -> None:
        request = AgentStrategyRequest.model_validate(
            {
                "scenario": "s1_external_input",
                "state": self._state(
                    turbidity=500, flow_rate=100, temperature=0, dissolved_oxygen=15
                ),
            }
        )
        self.assertEqual(request.state.turbidity, 500)


class AgentExplainRequestSchemaTest(unittest.TestCase):
    def test_accepts_scenario_and_state(self) -> None:
        request = AgentExplainRequest.model_validate(
            {
                "scenario": "s1_external_input",
                "state": {
                    "date": "2025-10-31",
                    "turbidity": 25.5,
                    "flow_rate": 28.5,
                },
            }
        )
        self.assertEqual(request.scenario, "s1_external_input")
        self.assertEqual(request.state.turbidity, 25.5)

    def test_requires_state(self) -> None:
        with self.assertRaises(ValidationError):
            AgentExplainRequest.model_validate({"scenario": "s1_external_input"})


if __name__ == "__main__":
    asyncio.run(unittest.main())
