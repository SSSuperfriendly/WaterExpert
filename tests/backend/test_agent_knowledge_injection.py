"""What the platform puts in the request body it sends to the agent.

The whole design rests on one property: the platform retrieves and the agent
consumes, so the only thing that crosses the wire is a dict attached to the
request. These tests pin what that dict's *absence* looks like as carefully as
its presence — an agent that has never heard of ``knowledge_context`` must still
receive a request it can serve, and that is what ``with_knowledge=false`` and a
failing retrieval both have to produce.
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.services import kg_service as kg_query
from tests.backend._helpers import admin_auth_guard

STATE = {
    "date": "2025-10-31",
    "turbidity": 41.0,
    "flow_rate": 3.2,
    "temperature": 18.2,
    "chlorophyll_a": 5.2,
    "rainfall_3d": 0.0,
}

AGENT_REPLY = {"job_id": "job-1", "status": "queued"}


def _context() -> dict:
    return {
        "version": "1",
        "query": "底泥再悬浮如何影响营养盐释放与水体浊度？",
        "scenario": "s2_internal_release",
        "mode": "local",
        "source": "baseline",
        "summary_text": "检索到 1 条关系。",
        "relations": [
            {
                "source": "底泥再悬浮",
                "relation": "增加",
                "target": "浊度",
                "evidence": "bottom sediment resuspension contributed to increased turbid conditions",
                "source_id": "platform",
                "source_label": "基线图谱",
            }
        ],
        "citations": [],
        "capabilities": {"chunk_level": False, "communities": True, "citations": True},
        "degraded": False,
    }


class AgentKnowledgeInjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        main.app.dependency_overrides[main.auth_guard] = admin_auth_guard
        main.app.dependency_overrides[main.current_actor] = lambda: "tester"
        self.client = TestClient(main.app)
        self.sent: list[dict] = []

        async def _capture(payload):
            self.sent.append(payload)
            return AGENT_REPLY

        self._strategy_patch = mock.patch.object(main.external_agent, "create_strategy", _capture)
        self._explain_patch = mock.patch.object(main.external_agent, "explain", _capture)
        self._strategy_patch.start()
        self._explain_patch.start()

    def tearDown(self) -> None:
        self._strategy_patch.stop()
        self._explain_patch.stop()
        main.app.dependency_overrides.clear()

    # ---- strategy: opt-in -------------------------------------------------

    def test_strategy_without_the_flag_sends_no_context(self) -> None:
        response = self.client.post(
            "/api/v1/agent/strategy",
            json={"scenario": "s2_internal_release", "state": STATE},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn("knowledge_context", self.sent[0])
        # The documented agent contract, unchanged.
        self.assertEqual(
            set(self.sent[0]), {"scenario", "state", "episodes", "backend"}
        )

    def test_strategy_with_the_flag_sends_the_retrieved_evidence(self) -> None:
        with mock.patch.object(
            main.kg_service, "build_agent_knowledge_context", return_value=_context()
        ):
            response = self.client.post(
                "/api/v1/agent/strategy",
                json={
                    "scenario": "s2_internal_release",
                    "state": STATE,
                    "with_knowledge": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        sent = self.sent[0]["knowledge_context"]
        self.assertEqual(sent["mode"], "local")
        self.assertEqual(sent["relations"][0]["source_id"], "platform")

    def test_a_failing_retrieval_still_sends_a_servable_request(self) -> None:
        """The graph must not become a new failure mode for the agent routes."""
        with mock.patch.object(
            main.kg_service,
            "build_agent_knowledge_context",
            side_effect=RuntimeError("parquet is unreadable"),
        ):
            response = self.client.post(
                "/api/v1/agent/strategy",
                json={
                    "scenario": "s2_internal_release",
                    "state": STATE,
                    "with_knowledge": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("knowledge_context", self.sent[0])

    # ---- explain: on by default -------------------------------------------

    def test_explain_attaches_the_context_by_default(self) -> None:
        with mock.patch.object(
            main.kg_service, "build_agent_knowledge_context", return_value=_context()
        ) as retrieve:
            response = self.client.post(
                "/api/v1/agent/explain",
                json={"scenario": "s2_internal_release", "state": STATE},
            )

        self.assertEqual(response.status_code, 200)
        retrieve.assert_called_once()
        self.assertEqual(self.sent[0]["knowledge_context"]["query"], _context()["query"])

    def test_explain_can_be_asked_not_to(self) -> None:
        with mock.patch.object(
            main.kg_service, "build_agent_knowledge_context", return_value=_context()
        ) as retrieve:
            self.client.post(
                "/api/v1/agent/explain",
                json={
                    "scenario": "s2_internal_release",
                    "state": STATE,
                    "with_knowledge": False,
                },
            )

        retrieve.assert_not_called()
        self.assertNotIn("knowledge_context", self.sent[0])

    def test_a_failing_retrieval_does_not_fail_the_explanation(self) -> None:
        with mock.patch.object(
            main.kg_service,
            "build_agent_knowledge_context",
            side_effect=RuntimeError("index will not build"),
        ):
            response = self.client.post(
                "/api/v1/agent/explain",
                json={"scenario": "s2_internal_release", "state": STATE},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("knowledge_context", self.sent[0])


class QueryBuilderTest(unittest.TestCase):
    """The scenario query the retrieval is run against, and how state joins it."""

    def test_every_scenario_has_a_query(self) -> None:
        for scenario in (
            "s1_external_input",
            "s2_internal_release",
            "s3_algae_bloom",
            "s4_chronic_combo",
        ):
            with self.subTest(scenario=scenario):
                query = kg_query.agent_query(scenario, {})
                self.assertTrue(query)
                self.assertIn(query, kg_query.AGENT_SCENARIO_QUERIES[scenario])

    def test_state_values_are_folded_in_when_they_are_plausible(self) -> None:
        query = kg_query.agent_query(
            "s2_internal_release", {"turbidity": 41.0, "flow_rate": 3.2}
        )
        self.assertIn("浊度约41.0", query)
        self.assertIn("流速约3.2", query)

    def test_implausible_values_are_left_out(self) -> None:
        """A zero or a nonsense reading must not steer retrieval.

        ``state`` is caller-supplied and the field is optional, so a ``0`` here
        usually means "not measured" rather than "zero turbidity".
        """
        query = kg_query.agent_query(
            "s2_internal_release",
            {"turbidity": 0, "chlorophyll_a": -1, "rainfall_3d": 10_000, "flow_rate": None},
        )
        # The scenario template itself names 浊度, so the assertion is on the
        # rendered reading ("浊度约41.0"), not on the word.
        self.assertNotIn("约", query)

    def test_an_unknown_scenario_still_yields_a_usable_question(self) -> None:
        self.assertTrue(kg_query.agent_query("not_a_scenario", {}))

    def test_a_boolean_is_not_read_as_a_measurement(self) -> None:
        """``True`` is an ``int`` in Python; it must not render as "浊度约1"."""
        self.assertNotIn(
            "约", kg_query.agent_query("s2_internal_release", {"turbidity": True})
        )


if __name__ == "__main__":
    unittest.main()
