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
from typing import ClassVar

from water_ai.agents import AquaTurbGPTAgent, KnowledgeBaseAgent
from water_ai.api.routes.explain import generate_explanation
from water_ai.api.schemas import KnowledgeContext
from water_ai.orchestrator.coordinator import Orchestrator

#: The keys every candidate carries, whatever it rests on. A consumer iterating
#: ``recommendations`` indexes these by name, so their *presence* is the
#: contract — and their *value* is the evidence, which is ``None`` wherever no
#: source recorded one.
PARAMETER_KEYS = (
    "technique",
    "origin",
    "intensity",
    "intensity_unit",
    "intensity_field",
    "cost_per_day",
    "case_id",
    "case_similarity",
    "reference",
    "source_label",
)


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
                "source_label": "基线图谱",
            },
            {
                "technique": "SEDIMENT",
                "relation": "",
                "evidence": "农业活动是土壤侵蚀和沉积物负荷增加的主要原因",
                "source_id": "inherited",
                "source_label": "继承图谱（合作方 GraphRAG）",
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

    def test_the_thresholds_survive_the_schema(self):
        """``extra="ignore"`` makes an undeclared field vanish without a word.

        So the thresholds are declared, and this is the test that keeps them
        declared: drop the field from ``KnowledgeContext`` and the platform
        still sends ten levels, ``model_dump`` still carries them, and CMFBE
        finds none — a failure invisible from both ends, because each side is
        internally consistent. It is the same shape as the drift this section
        was added to end.
        """
        payload = _context(
            thresholds={
                "available": True,
                "graph_name": "mechanism_parameter_threshold_knowledge_graph",
                "scope": "wusongkou_daily_prototype",
                "semantics": "empirical critical levels",
                "guardrails": ["Do not reinterpret these as calibrated 2D thresholds."],
                "nodes": [
                    {
                        "node_id": "threshold::precipitation_3d",
                        "feature": "precipitation_3d",
                        "label": "3-day cumulative precipitation",
                        "threshold": 49.1,
                        "unit": "mm",
                        "response": "net_process_response",
                        "r2_gain": 0.2506,
                        "piecewise_r2": 0.4057,
                        "response_jump": 0.4091,
                        "interpretation": "Higher-than-threshold values force turbidity.",
                    }
                ],
                "contextual_nodes": [],
                "notes": [],
            }
        )
        context = KnowledgeContext.model_validate(payload)

        self.assertIsNotNone(context.thresholds)
        dumped = context.model_dump()
        self.assertTrue(dumped["thresholds"]["available"])
        node = dumped["thresholds"]["nodes"][0]
        self.assertEqual(node["feature"], "precipitation_3d")
        self.assertEqual(node["threshold"], 49.1)
        self.assertEqual(node["unit"], "mm")
        self.assertEqual(node["r2_gain"], 0.2506)

    def test_a_context_without_thresholds_is_not_an_error(self):
        """An older platform sends none, which is a fact and not a failure."""
        self.assertIsNone(KnowledgeContext.model_validate(_context()).thresholds)


class KnowledgeBaseAgentTest(unittest.TestCase):
    def test_without_a_context_nothing_changes(self):
        """The pre-GraphRAG contract: the scenario's own vocabulary, no graph."""
        agent = KnowledgeBaseAgent()
        result = agent.act({"scenario_type": "s2_internal_release"})

        self.assertEqual(result["source"], "KnowledgeBaseAgent")
        self.assertNotIn("grounded", result)
        self.assertEqual(
            [item["technique"] for item in result["recommendations"]],
            ["精细化流量控制", "原位曝气"],
        )
        for item in result["recommendations"]:
            self.assertEqual(item["origin"], "scenario")

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

    def test_every_candidate_carries_the_shape_downstream_stages_index(self):
        """A missing parameter must become neither a KeyError nor a plausible number."""
        agent = KnowledgeBaseAgent()
        result = agent.act(
            {"scenario_type": "s2_internal_release", "knowledge_context": _context()}
        )

        self.assertTrue(result["recommendations"])
        for item in result["recommendations"]:
            for key in PARAMETER_KEYS:
                self.assertIn(key, item, f"{item.get('technique')} is missing {key}")

    def test_a_graph_candidate_reports_no_parameters_rather_than_inventing_them(self):
        """The edge says wind resuspends sediment. It does not say how much."""
        agent = KnowledgeBaseAgent()
        result = agent.act(
            {"scenario_type": "s2_internal_release", "knowledge_context": _context()}
        )

        grounded = [r for r in result["recommendations"] if r["origin"] == "graph"]
        self.assertTrue(grounded)
        for item in grounded:
            self.assertIsNone(item["intensity"])
            self.assertIsNone(item["intensity_unit"])
            self.assertIsNone(item["cost_per_day"])
            self.assertIsNone(item["case_id"])

    def test_graph_candidates_carry_their_citation_and_provenance(self):
        agent = KnowledgeBaseAgent()
        result = agent.act(
            {"scenario_type": "s2_internal_release", "knowledge_context": _context()}
        )

        first = result["recommendations"][0]
        self.assertEqual(first["technique"], "沉积物再悬浮")
        self.assertEqual(first["evidence"], "Wind-induced disturbances")
        self.assertEqual(first["source_id"], "platform")
        # The graph under its own name: "platform" is an id, 基线图谱 is what the
        # platform calls that graph when it shows it to a reader.
        self.assertEqual(first["source_label"], "基线图谱")
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


class CaseBackedParametersTest(unittest.TestCase):
    """The knowledge base's numbers, and where each of them came from.

    The scenario vocabulary used to be priced from two module constants, so
    every technique it proposed carried an intensity of 0.5 and a cost of zero
    that no document supported. These tests pin the replacement: a number is the
    one a documented intervention recorded, it names the case it came from, and
    where nothing recorded one the entry says so instead of picking a default.
    """

    #: Case 003's own condition, so it is the closest match by construction and
    #: the expected parameters are the ones printed in the library.
    DIANCHI: ClassVar[dict[str, float]] = {"turbidity": 18.7, "flow_rate": 12.5, "rainfall_3d": 8.0}

    def test_the_scenario_entries_are_priced_by_a_published_case(self):
        result = KnowledgeBaseAgent().act(
            {"scenario_type": "s2_internal_release", **self.DIANCHI}
        )

        by_technique = {item["technique"]: item for item in result["recommendations"]}
        flow = by_technique["精细化流量控制"]
        self.assertEqual((flow["intensity"], flow["intensity_unit"]), (2.5, "m³/s"))
        self.assertEqual(flow["intensity_field"], "release_rate")
        self.assertEqual(flow["case_id"], "case_003")
        self.assertTrue(flow["reference"])

        aeration = by_technique["原位曝气"]
        self.assertEqual((aeration["intensity"], aeration["intensity_unit"]), (18.0, "kW"))
        self.assertEqual(aeration["intensity_field"], "aeration_intensity")
        self.assertEqual(aeration["case_id"], "case_003")

    def test_the_case_quoted_is_the_one_most_like_the_current_water(self):
        """A number is only informative if it came off a comparable water body."""
        result = KnowledgeBaseAgent().act(
            {"scenario_type": "s1_external_input", "turbidity": 32.5, "flow_rate": 35.2, "rainfall_3d": 52.0}
        )

        by_technique = {item["technique"]: item for item in result["recommendations"]}
        self.assertEqual(by_technique["加大放水冲刷"]["case_id"], "case_001")
        self.assertEqual(by_technique["加大放水冲刷"]["intensity"], 5.2)

    def test_a_technique_no_case_supports_is_offered_without_a_number(self):
        """增加沉淀池反冲 is a real option and the library records nothing for it."""
        result = KnowledgeBaseAgent().act(
            {"scenario_type": "s1_external_input", "turbidity": 32.5, "flow_rate": 35.2, "rainfall_3d": 52.0}
        )

        by_technique = {item["technique"]: item for item in result["recommendations"]}
        unsupported = by_technique["增加沉淀池反冲"]
        self.assertIsNone(unsupported["intensity"])
        self.assertIsNone(unsupported["intensity_unit"])
        self.assertIsNone(unsupported["case_id"])
        self.assertEqual(unsupported["reference"], "")

    def test_a_scenario_the_library_does_not_document_borrows_no_numbers(self):
        """The failure mode is a case from another scenario lending its dose."""
        result = KnowledgeBaseAgent().act(
            {"scenario_type": "s9_undocumented", **self.DIANCHI}
        )

        self.assertEqual(result["case_evidence"], [])
        self.assertTrue(result["recommendations"])
        for item in result["recommendations"]:
            self.assertIsNone(item["intensity"])
            self.assertIsNone(item["case_id"])

    def test_the_evidence_is_the_same_record_the_explanation_shows(self):
        """A recommendation's case id has to resolve to a case the user can read."""
        result = KnowledgeBaseAgent().act(
            {"scenario_type": "s2_internal_release", **self.DIANCHI}
        )

        evidence = result["case_evidence"]
        self.assertTrue(evidence)
        best = evidence[0]
        self.assertEqual(best["id"], "case_003")
        self.assertEqual(best["scenario"], "s2_internal_release")
        self.assertEqual(best["similarity"], 1.0)
        self.assertEqual(best["intervention"]["aeration_intensity"], 18.0)
        self.assertIn("recovery_days", best["outcome"])

        cited = {
            item["case_id"]
            for item in result["recommendations"]
            if item["case_id"]
        }
        self.assertEqual(cited, {"case_003"})

    def test_a_scenario_the_seed_rows_cover_names_the_technology(self):
        """The quadruples key on ``technology``; consumers index ``technique``."""
        result = KnowledgeBaseAgent().act({"scenario_type": "s9_undocumented"})

        self.assertTrue(result["recommendations"])
        self.assertEqual(
            [item["origin"] for item in result["recommendations"]], ["seed", "seed"]
        )
        self.assertEqual(
            [item["technique"] for item in result["recommendations"]],
            ["aeration", "controlled_release"],
        )


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
