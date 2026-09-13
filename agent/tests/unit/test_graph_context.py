"""Agent-side consumption of the graph evidence the platform injects.

The platform retrieves and the agent consumes; the agent never calls back. These
tests pin the consuming half: that the payload is accepted without a version
lockstep, that a graph-grounded request actually changes what the knowledge base
answers, and that a request *without* a context behaves exactly as it did before
GraphRAG existed — which is the property that makes this rollout additive rather
than a flag day.
"""

import asyncio
import unittest

from water_ai.agents import AquaTurbGPTAgent, KnowledgeBaseAgent
from water_ai.api.routes.explain import generate_explanation
from water_ai.api.schemas import KnowledgeContext
from water_ai.orchestrator.coordinator import Orchestrator


def _context(**overrides):
    """A context shaped exactly like the platform's, with one edge from each graph.

    The field set is copied from a real ``build_agent_knowledge_context``
    response rather than invented. That matters here: an invented fixture would
    have hidden the fact that the platform's ``recommendations`` entries carry
    no ``origin`` key, and a filter written against one would have silently
    rendered nothing against the other.
    """
    payload = {
        "version": "1",
        "query": "底泥再悬浮如何影响营养盐释放与水体浊度？",
        "scenario": "s2_internal_release",
        "mode": "local",
        "source": "baseline",
        "summary_text": "检索到 2 条关系。",
        "relations": [
            {
                "source": "风",
                "relation": "导致",
                "target": "沉积物再悬浮",
                "evidence": "Wind-induced disturbances",
                "source_id": "platform",
                "source_label": "基线图谱",
                "source_file": "clean_a (4).txt",
                "chunk_id": None,
            },
            {
                "source": "AGRICULTURE",
                "relation": "",
                "target": "SEDIMENT",
                "evidence": "农业活动是土壤侵蚀和沉积物负荷增加的主要原因",
                "source_id": "inherited",
                "source_label": "继承图谱（合作方 GraphRAG）",
                "source_file": "create_final_relationships.parquet",
                "chunk_id": None,
            },
        ],
        "recommendations": [
            {
                "technique": "沉积物再悬浮",
                "relation": "导致",
                "evidence": "Wind-induced disturbances",
                "source_id": "platform",
            },
            {
                "technique": "SEDIMENT",
                "relation": "",
                "evidence": "农业活动是土壤侵蚀和沉积物负荷增加的主要原因",
                "source_id": "inherited",
            },
        ],
        "citations": [
            {
                "marker": "[关系1]",
                "kind": "relation",
                "source_id": "platform",
                "source": "风",
                "relation": "导致",
                "target": "沉积物再悬浮",
                "evidence": "Wind-induced disturbances",
                "source_file": "clean_a (4).txt",
                "chunk_id": None,
            },
            {
                "marker": "[关系2]",
                "kind": "relation",
                "source_id": "inherited",
                "source": "AGRICULTURE",
                "relation": "",
                "target": "SEDIMENT",
                "evidence": "农业活动是土壤侵蚀和沉积物负荷增加的主要原因",
                "source_file": "create_final_relationships.parquet",
                "chunk_id": None,
            },
        ],
        "paths": [
            {"source_id": "platform", "nodes": ["风", "沉积物再悬浮"], "hops": 1, "score": 0.71}
        ],
        "capabilities": {"chunk_level": False, "communities": True, "citations": True},
        "degraded": False,
        "notes": [],
    }
    payload.update(overrides)
    return payload


class KnowledgeContextSchemaTest(unittest.TestCase):
    def test_unknown_fields_are_ignored_rather_than_rejected(self):
        """A newer platform must not break an older agent.

        pydantic v2 already behaves this way; the model declares it, and this
        test is what keeps the declaration honest if someone narrows it later.
        """
        payload = _context()
        payload["a_field_from_a_future_platform"] = {"nested": True}
        payload["relations"][0]["another_future_field"] = "x"

        context = KnowledgeContext.model_validate(payload)

        self.assertEqual(len(context.relations), 2)
        self.assertFalse(hasattr(context, "a_field_from_a_future_platform"))

    def test_an_empty_payload_yields_an_inert_context(self):
        empty = KnowledgeContext.model_validate({})
        self.assertEqual(empty.mode, "none")
        self.assertEqual(empty.source, "none")
        self.assertEqual(empty.relations, [])
        self.assertFalse(empty.degraded)

    def test_each_relation_keeps_the_graph_it_came_from(self):
        context = KnowledgeContext.model_validate(_context())
        self.assertEqual(
            [(r.source_id, r.source_label) for r in context.relations],
            [("platform", "基线图谱"), ("inherited", "继承图谱（合作方 GraphRAG）")],
        )


class KnowledgeBaseAgentTest(unittest.TestCase):
    def test_without_a_context_nothing_changes(self):
        """The pre-GraphRAG contract, byte for byte."""
        agent = KnowledgeBaseAgent()
        result = agent.act({"scenario_type": "s2_internal_release"})

        self.assertEqual(result["source"], "KnowledgeBaseAgent")
        self.assertNotIn("grounded", result)
        self.assertEqual(
            [item["technique"] for item in result["recommendations"]],
            ["精细化流量控制", "原位曝气"],
        )
        for item in result["recommendations"]:
            self.assertNotIn("origin", item)

    def test_a_graph_context_puts_retrieved_edges_first(self):
        agent = KnowledgeBaseAgent()
        result = agent.act(
            {
                "scenario_type": "s2_internal_release",
                "knowledge_context": _context(),
            }
        )

        self.assertEqual(result["source"], "KnowledgeBaseAgent+GraphRAG")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["graph_mode"], "local")
        self.assertEqual(result["graph_query"], _context()["query"])
        self.assertEqual(result["recommendations"][0]["technique"], "沉积物再悬浮")
        self.assertEqual(result["recommendations"][0]["origin"], "graph")
        # The curated entries follow rather than being replaced: the graph knows
        # the literature, the dictionary knows what treatment costs to run.
        self.assertIn("精细化流量控制", [r["technique"] for r in result["recommendations"]])

    def test_graph_candidates_carry_the_shape_downstream_stages_index(self):
        """A missing price must not become a KeyError three stages later."""
        agent = KnowledgeBaseAgent()
        result = agent.act(
            {"scenario_type": "s2_internal_release", "knowledge_context": _context()}
        )

        grounded = [r for r in result["recommendations"] if r.get("origin") == "graph"]
        self.assertTrue(grounded)
        for item in grounded:
            self.assertIsInstance(item["intensity"], float)
            self.assertIsInstance(item["cost_per_day"], float)

    def test_graph_candidates_carry_their_citation_and_provenance(self):
        agent = KnowledgeBaseAgent()
        result = agent.act(
            {"scenario_type": "s2_internal_release", "knowledge_context": _context()}
        )

        first = result["recommendations"][0]
        self.assertEqual(first["technique"], "沉积物再悬浮")
        self.assertEqual(first["evidence"], "Wind-induced disturbances")
        self.assertEqual(first["source_id"], "platform")
        self.assertEqual(first["citation"], "[关系1]")

    def test_an_empty_context_falls_back_to_the_curated_dictionary(self):
        agent = KnowledgeBaseAgent()
        result = agent.act(
            {
                "scenario_type": "s2_internal_release",
                "knowledge_context": {"relations": [], "recommendations": []},
            }
        )
        self.assertEqual(result["source"], "KnowledgeBaseAgent")


class SummarizeDiagnosisTest(unittest.TestCase):
    """The half the old two-argument signature could not reach.

    ``primary_drivers`` used to render as ``Unknown`` on every real request —
    not a misspelled key, but the coordinator handing over nested stage-1
    reports while the prompt read them as if they were already flat.
    """

    def setUp(self):
        self.agent = AquaTurbGPTAgent(config={"deepseek": {"backend": "local"}})
        self.reports = {
            "mscim": {
                "diagnosis": {
                    "primary_drivers": [
                        {"factor": "external_rainfall", "importance": 0.8},
                        {"factor": "algae_growth", "importance": 0.62},
                    ]
                },
                "prediction": {"turbidity_confidence": 0.77},
            },
            "cmfbe": {"net_change": -0.1234},
            "knowledge_base": {"recommendations": []},
        }

    def test_nested_reports_become_the_fields_the_prompt_asks_for(self):
        summary = self.agent._summarize_diagnosis(
            {"turbidity": 41.0, "flow_rate": 3.2}, self.reports
        )
        self.assertEqual(summary["primary_drivers"], "external_rainfall(0.80), algae_growth(0.62)")
        self.assertEqual(summary["confidence"], "0.77")
        self.assertEqual(summary["flow_condition"], "低（3.2 m³/s）")
        self.assertEqual(summary["turbidity"], 41.0)
        self.assertEqual(summary["net_change"], "-0.123")

    def test_flow_condition_banding(self):
        for rate, expected in ((0.4, "低"), (5.0, "中"), (20.0, "中"), (28.5, "高")):
            with self.subTest(flow_rate=rate):
                summary = self.agent._summarize_diagnosis({"flow_rate": rate}, self.reports)
                self.assertTrue(summary["flow_condition"].startswith(expected))

    def test_nothing_available_renders_as_unknown_rather_than_crashing(self):
        summary = self.agent._summarize_diagnosis({}, {})
        self.assertEqual(summary["primary_drivers"], "Unknown")
        self.assertEqual(summary["confidence"], "Unknown")
        self.assertEqual(summary["flow_condition"], "Unknown")

    def test_the_prompt_reaches_the_model_with_real_drivers(self):
        prompt = self.agent._build_strategy_prompt(
            "s2_internal_release", self.reports, state={"turbidity": 41.0, "flow_rate": 3.2}
        )
        self.assertIn("external_rainfall(0.80)", prompt)
        self.assertNotIn("主要驱动因素: Unknown", prompt)

    def test_a_flat_diagnosis_is_used_as_given(self):
        """Both call conventions hold, so neither caller silently shows Unknown."""
        prompt = self.agent._build_strategy_prompt(
            "s2_internal_release", {"primary_drivers": "sediment(0.5)", "confidence": "0.90"}
        )
        self.assertIn("sediment(0.5)", prompt)
        self.assertIn("0.90", prompt)

    def test_the_prompt_carries_the_retrieved_evidence(self):
        """Retrieval that never reaches the prompt is retrieval that never happened."""
        prompt = self.agent._build_strategy_prompt(
            "s2_internal_release",
            self.reports,
            state={"turbidity": 41.0, "flow_rate": 3.2},
            knowledge_context=_context(),
        )
        self.assertIn("图谱依据", prompt)
        self.assertIn("风 --导致--> 沉积物再悬浮", prompt)
        self.assertIn("农业活动是土壤侵蚀和沉积物负荷增加的主要原因", prompt)
        self.assertIn("继承图谱（合作方 GraphRAG）", prompt)
        # Edges' targets are offered as concepts, not as measures — on the real
        # graphs they are factors and processes, and a model told they were
        # candidate measures would recommend resuspending sediment.
        self.assertIn("图谱中最相关的概念：沉积物再悬浮、SEDIMENT", prompt)
        self.assertNotIn("候选方向", prompt)

    def test_no_context_leaves_the_prompt_without_a_graph_section(self):
        prompt = self.agent._build_strategy_prompt(
            "s2_internal_release", self.reports, state={"turbidity": 41.0}
        )
        self.assertNotIn("图谱依据", prompt)


class CoordinatorThreadingTest(unittest.TestCase):
    def _agents(self):
        return {
            "KnowledgeBaseAgent": KnowledgeBaseAgent(),
            "AquaTurbGPTAgent": AquaTurbGPTAgent(config={"deepseek": {"backend": "local"}}),
        }

    def test_the_context_reaches_the_knowledge_base_and_the_trace(self):
        orchestrator = Orchestrator()
        result = orchestrator.run(
            self._agents(),
            {"turbidity": 41.0, "flow_rate": 3.2},
            scenario_key="s2_internal_release",
            knowledge_context=_context(),
        )

        kb_output = result["diagnosis"]["knowledge_base"]
        self.assertEqual(kb_output["source"], "KnowledgeBaseAgent+GraphRAG")
        self.assertTrue(result["agent_traces"]["kb"]["input"]["knowledge_context_available"])
        self.assertEqual(
            result["agent_traces"]["kb"]["input"]["knowledge_context_query"], _context()["query"]
        )
        self.assertTrue(result["agent_traces"]["gpt"]["input"]["knowledge_context_available"])

    def test_omitting_the_context_is_the_pre_graphrag_behaviour(self):
        orchestrator = Orchestrator()
        result = orchestrator.run(
            self._agents(), {"turbidity": 41.0}, scenario_key="s2_internal_release"
        )

        self.assertEqual(result["diagnosis"]["knowledge_base"]["source"], "KnowledgeBaseAgent")
        self.assertFalse(result["agent_traces"]["kb"]["input"]["knowledge_context_available"])

    def test_state_is_not_polluted_with_the_context(self):
        """``state`` is indexed by feature name downstream; an extra key there breaks it."""
        orchestrator = Orchestrator()
        state = {"turbidity": 41.0, "flow_rate": 3.2}
        orchestrator.run(
            self._agents(), state, scenario_key="s2_internal_release", knowledge_context=_context()
        )
        self.assertEqual(set(state), {"turbidity", "flow_rate"})


class ExplainRouteTest(unittest.TestCase):
    def _post(self, payload):
        return asyncio.run(generate_explanation(payload))

    def test_a_context_is_rendered_and_reported(self):
        response = self._post(
            {
                "scenario": "s2_internal_release",
                "state": {"turbidity": 41.0, "flow_rate": 3.2, "rainfall_3d": 1.0},
                "knowledge_context": _context(),
            }
        )

        self.assertTrue(response["knowledge_context_available"])
        self.assertIn("【图谱依据】", response["explanation"])
        self.assertIn("风 --导致--> 沉积物再悬浮（基线图谱）", response["explanation"])
        # The edge with no relation label renders its description instead — the
        # inherited graph has no relation types at all.
        self.assertIn("--农业活动是土壤侵蚀和沉积物负荷增加的主要原因-->", response["explanation"])
        # The case library section is still there; the graph section is additive.
        self.assertIn("【综合建议】", response["explanation"])

    def test_without_a_context_the_explanation_is_unchanged(self):
        base = self._post(
            {
                "scenario": "s2_internal_release",
                "state": {"turbidity": 41.0, "flow_rate": 3.2, "rainfall_3d": 1.0},
            }
        )
        self.assertFalse(base["knowledge_context_available"])
        self.assertNotIn("【图谱依据】", base["explanation"])

    def test_a_malformed_context_degrades_instead_of_failing_the_request(self):
        """The lab page posts this payload ad hoc; a bad context is not a 500."""
        response = self._post(
            {
                "scenario": "s2_internal_release",
                "state": {"turbidity": 41.0},
                "knowledge_context": "not an object",
            }
        )
        self.assertFalse(response["knowledge_context_available"])
        self.assertIn("【综合建议】", response["explanation"])

    def test_the_existing_response_contract_is_untouched(self):
        response = self._post({"scenario": "s1_external_input", "state": {"turbidity": 30.0}})
        for key in ("scenario", "explanation", "matched_cases"):
            self.assertIn(key, response)


if __name__ == "__main__":
    unittest.main()
