"""The payload the platform hands the agent, against the real graphs.

``build_agent_knowledge_context`` is the whole interface between the two
services: the platform retrieves, the agent consumes, and nothing else crosses.
Its shape is therefore a contract, and the tests elsewhere that pin it all patch
it out with a hand-written fixture — which is the right way to test the routes
and the wrong way to test the payload, because a fixture can only assert what
its author already believed the payload contained.

This module runs the real retrieval over the repository's own graphs and checks
what a consumer would actually receive: that both graphs reach it, that every
candidate names the graph it came from under the name a reader is shown, and
that the candidates and the relations agree about which graph that is. It is the
same approach ``test_graph_rag_eval`` takes, and for the same reason.

``runtime_root`` is the project root, not ``var/``. That is not a detail: the
committed platform graph is resolved as ``outputs_root / "knowledge_graph"`` and
``outputs_root`` is ``runtime_root / "outputs"``, so a fixture that points the
runtime root at ``var/`` looks for ``var/outputs/knowledge_graph``, finds
nothing, and quietly serves the inherited graph alone. Every assertion below
would still pass — the payload would simply be missing the platform's own
curated edges, which is the failure this module exists to catch.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.config import Settings
from backend.app.services.kg_service import KnowledgeGraphService

REPO_ROOT = Path(__file__).resolve().parents[2]

SCENARIO_STATE = {"turbidity": 41.0, "flow_rate": 3.2, "rainfall_3d": 1.0}

SCENARIOS = (
    "s1_external_input",
    "s2_internal_release",
    "s3_algae_bloom",
    "s4_chronic_combo",
)


def make_settings() -> Settings:
    """The settings the deployed platform runs under, not a sandbox.

    ``runtime_root`` is the project root — see the module docstring. The two
    roots that stay under ``var/`` are the ones the service writes to; nothing
    here writes, and pointing them at a temporary directory would not change
    what is read.
    """
    return Settings(
        app_name="test",
        project_root=REPO_ROOT,
        runtime_root=REPO_ROOT,
        frontend_root=REPO_ROOT / "frontend" / "out",
        report_root=REPO_ROOT / "var" / "reports",
        state_root=REPO_ROOT / "var" / "state",
    )


class AgentKnowledgeContextPayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = KnowledgeGraphService(make_settings())
        cls.context = cls.service.build_agent_knowledge_context(
            "s2_internal_release", SCENARIO_STATE
        )

    def test_the_graph_retrieval_actually_returned_something(self) -> None:
        """A payload of empty lists would satisfy every assertion below."""
        self.assertEqual(self.context["mode"], "local")
        self.assertTrue(self.context["relations"], self.context.get("notes"))

    def test_both_graphs_reach_the_agent_for_every_scenario(self) -> None:
        """The connection the platform exists to make, asserted end to end.

        The curated graph is Chinese and operator-facing; the inherited one is
        an English literature export. The agent has no other way to see the
        former, and a bundle that silently lost it would leave the control loop
        reasoning entirely from translated literature — which is exactly what
        happens when ``baseline_dir`` resolves to a directory that is not there.
        """
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                context = self.service.build_agent_knowledge_context(scenario, SCENARIO_STATE)
                seen = {relation["source_id"] for relation in context["relations"]}
                self.assertIn("platform", seen, context.get("notes"))
                self.assertIn("inherited", seen, context.get("notes"))

    def test_each_candidate_names_the_graph_it_came_from(self) -> None:
        """``source_id`` is an id; the label is what the platform calls the graph.

        The agent reports graph candidates as a list of their own, apart from
        the relations they were built from, so the label has to travel with the
        candidate. Without it the agent's plan can only say ``platform``.
        """
        for candidate in self.context["recommendations"]:
            with self.subTest(technique=candidate["technique"]):
                self.assertTrue(candidate["source_id"])
                self.assertTrue(candidate["source_label"])

    def test_every_relation_is_attributed_to_a_graph(self) -> None:
        """A blank ``source_id`` renders as an edge with no origin at all.

        The id is recovered from the citation that carries it, not from the
        relation, so a relation that reached ``matched_relations`` without one
        would arrive unattributed — and an unattributed edge is the one thing a
        reader cannot check.
        """
        for relation in self.context["relations"]:
            with self.subTest(relation=f"{relation['source']}->{relation['target']}"):
                self.assertTrue(relation["source_id"])
                self.assertTrue(relation["source_label"])

    def test_the_two_graphs_are_not_labelled_the_same(self) -> None:
        labels = {
            relation["source_id"]: relation["source_label"]
            for relation in self.context["relations"]
        }
        self.assertNotEqual(labels["platform"], labels["inherited"])

    def test_candidates_and_relations_agree_about_which_graph_is_which(self) -> None:
        """One graph must not be 基线图谱 in one list and 继承图谱 in the other."""
        by_id = {
            relation["source_id"]: relation["source_label"]
            for relation in self.context["relations"]
            if relation["source_id"]
        }
        self.assertTrue(by_id)
        for candidate in self.context["recommendations"]:
            if candidate["source_id"] in by_id:
                self.assertEqual(candidate["source_label"], by_id[candidate["source_id"]])

    def test_a_candidate_carries_the_evidence_that_makes_it_checkable(self) -> None:
        for candidate in self.context["recommendations"]:
            with self.subTest(technique=candidate["technique"]):
                self.assertTrue(candidate["evidence"] or candidate["relation"])

    def test_the_payload_keeps_the_agent_request_contract(self) -> None:
        """The keys the deployed agent schema reads, and no others it must not."""
        for key in ("version", "query", "scenario", "mode", "source", "relations", "recommendations"):
            self.assertIn(key, self.context)
        self.assertNotIn("chunks", self.context)
        for relation in self.context["relations"]:
            self.assertNotIn("excerpt", relation)


if __name__ == "__main__":
    unittest.main()
