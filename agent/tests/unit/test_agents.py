import unittest
from pathlib import Path

import torch

from water_ai.agents import (
    MSCIMAgent,
    CMFBEAgent,
    KnowledgeBaseAgent,
    AquaTurbGPTAgent,
    RLTGRRAgent,
    SafetyAgent,
)
from water_ai.agents.checkpoint_inference import TimeSeriesCheckpointRunner


class TestAgents(unittest.TestCase):
    def test_agent_status(self):
        agents = [
            MSCIMAgent(),
            CMFBEAgent(),
            KnowledgeBaseAgent(),
            AquaTurbGPTAgent(config={"deepseek": {"backend": "local"}}),
            RLTGRRAgent(),
            SafetyAgent(),
        ]
        for agent in agents:
            status = agent.status()
            self.assertIn("name", status)
            self.assertEqual(status["type"], type(agent).__name__)

    def test_safety_constraints(self):
        safety = SafetyAgent(config={"constraints": {"max_release": 0.2}})
        result = safety.act({"release_rate": 1.0})
        self.assertLessEqual(result["safe_action"]["release_rate"], 0.2)

    def test_mscim_and_cmfbe_use_checkpoints_when_available(self):
        state = {
            "date": "2025-10-31",
            "turbidity": 25.5,
            "flow_rate": 28.5,
            "temperature": 18.2,
            "ph": 7.5,
            "dissolved_oxygen": 8.3,
            "chlorophyll_a": 5.2,
            "rainfall_3d": 45.3,
            "rainfall_7d": 120.5,
        }

        mscim_result = MSCIMAgent(config={"device": "cpu"}).act(state)
        cmfbe_result = CMFBEAgent(config={"device": "cpu"}).act(state)

        self.assertEqual(mscim_result["inference_source"], "checkpoint")
        self.assertEqual(cmfbe_result["inference_source"], "checkpoint")
        self.assertIn("turbidity", mscim_result["prediction"])
        self.assertIn("next_day_turbidity", cmfbe_result["predictions"])


class LookbackWindowTest(unittest.TestCase):
    """The architecture has to come off the checkpoint, not off a default.

    Every checkpoint in ``outputs/models`` was trained on a 21-day window and
    both prototypes default to 32. The window was the one dimension
    ``_model_kwargs`` did not derive from the state dict, so ``load_state_dict``
    rejected every one of them — and a rejected checkpoint does not raise, it
    silently downgrades the agent to rule-based inference. These tests pin the
    derivation without needing the 18 MB checkpoints on disk.
    """

    def runner(self) -> TimeSeriesCheckpointRunner:
        return TimeSeriesCheckpointRunner(
            checkpoint_path="outputs/models/mscim.pt", model_kind="mscim"
        )

    def test_the_window_is_read_off_the_position_embedding(self):
        state_dict = {"position_embedding": torch.zeros(1, 21, 64)}
        self.assertEqual(self.runner()._sequence_length(state_dict), 21)

    def test_the_cmfbe_key_is_read_too(self):
        state_dict = {"backbone.position_embedding": torch.zeros(1, 21, 64)}
        self.assertEqual(self.runner()._sequence_length(state_dict), 21)

    def test_a_checkpoint_without_one_falls_back_to_its_recorded_history(self):
        runner = self.runner()
        runner.history_days = 21
        self.assertEqual(runner._sequence_length({}), 21)


class ReadinessTest(unittest.TestCase):
    """``ready`` has to be a fact about the checkpoint, not about traffic.

    ``model`` stays ``None`` until the first prediction, so a health check that
    only looks at it calls a cold, healthy agent broken — and then calls it
    healthy the moment a request warms it. Both readings are wrong, and the
    second is the worse of the two: it is the 2026-09-08 sign-off again, where
    the signal that cleared the swap could not fail because nothing had asked
    it a question it could fail.
    """

    def test_a_cold_runner_answers_by_loading_rather_than_looking(self):
        runner = TimeSeriesCheckpointRunner(checkpoint_path="/nonexistent/x.pt", model_kind="mscim")
        self.assertIsNone(runner.model)
        self.assertFalse(runner.ready)
        # Not "not yet asked": asked, and the answer is no.
        self.assertTrue(runner.loaded)
        self.assertIn("not found", runner.load_error or "")

    def test_a_degraded_agent_says_so_on_a_server_that_has_served_nothing(self):
        agent = MSCIMAgent()
        agent.runner.checkpoint_path = Path("/nonexistent/x.pt")
        health = agent.health()
        self.assertEqual(health["status"], "degraded")
        self.assertFalse(health["checkpoint_loaded"])
        self.assertTrue(health["checkpoint_error"])


def graph_context(*nodes, available=True):
    """A knowledge context carrying a threshold graph, as the platform sends one."""
    return {
        "thresholds": {
            "available": available,
            "graph_name": "mechanism_parameter_threshold_knowledge_graph",
            "scope": "wusongkou_daily_prototype",
            "semantics": "empirical critical levels",
            "guardrails": ["Do not reinterpret these as calibrated 2D thresholds."],
            "nodes": list(nodes),
            "contextual_nodes": [],
            "notes": [],
        }
    }


def node(feature, threshold, unit="mm", **extra):
    return {
        "node_id": f"threshold::{feature}",
        "feature": feature,
        "label": f"{feature} label",
        "threshold": threshold,
        "unit": unit,
        "response": "net_process_response",
        "r2_gain": 0.25,
        "piecewise_r2": 0.4,
        "response_jump": 0.41,
        "interpretation": "Higher values force turbidity in this prototype.",
        **extra,
    }


class ThresholdSourceTest(unittest.TestCase):
    """Where a threshold comes from, and the fact that it is now said out loud.

    CMFBE used to screen against four numbers written into its own source. One
    of them had drifted from the platform's threshold graph — the agent called
    35.9 mm of 3-day rain critical while ``precipitation_3d`` in the graph was
    49.1 — so for a state between the two the agent reported a breach that the
    platform's own analysis does not recognise. Nothing in the output could show
    this, because a threshold held as a literal has no provenance to disagree
    with. These tests are that disagreement, made checkable.
    """

    def test_the_graphs_level_is_used_when_the_platform_sends_one(self):
        agent = CMFBEAgent()
        result = agent.act(
            {"precipitation_3d": 60.0},
            graph_context(node("precipitation_3d", 49.1)),
        )
        self.assertEqual(result["threshold_source"], "knowledge_graph")
        self.assertEqual(result["thresholds"]["precipitation_3d"], 49.1)

    def test_rain_between_the_old_number_and_the_real_one_is_not_a_breach(self):
        """The regression itself: 41 mm was a breach only because of the drift."""
        agent = CMFBEAgent()
        result = agent.act(
            {"precipitation_3d": 41.0},
            graph_context(node("precipitation_3d", 49.1)),
        )
        self.assertEqual(result["threshold_breaches"], [])

    def test_the_same_rain_above_the_real_level_is_a_breach(self):
        # The other half of the pair: the fix must not be "stop reporting".
        agent = CMFBEAgent()
        result = agent.act(
            {"precipitation_3d": 52.0},
            graph_context(node("precipitation_3d", 49.1)),
        )
        breaches = result["threshold_breaches"]
        self.assertEqual(len(breaches), 1)
        self.assertEqual(breaches[0]["factor"], "precipitation_3d")
        self.assertEqual(breaches[0]["value"], 52.0)
        self.assertEqual(breaches[0]["threshold"], 49.1)

    def test_a_breach_carries_the_shape_the_platform_documents(self):
        """``factor``/``value``/``threshold`` — all three, all numbers.

        The old entry was ``{"threshold": "rainfall_3d", "value": 41.0}``: a
        feature *name* under the key that means the level, and no ``factor`` at
        all. The frontend renders exactly these three fields, so it drew a blank
        factor and the name again where the threshold belongs.
        """
        agent = CMFBEAgent()
        result = agent.act({"precipitation_3d": 52.0}, graph_context(node("precipitation_3d", 49.1)))
        breach = result["threshold_breaches"][0]
        self.assertIsInstance(breach["factor"], str)
        self.assertIsInstance(breach["value"], float)
        self.assertIsInstance(breach["threshold"], float)
        self.assertEqual(breach["unit"], "mm")

    def test_the_graphs_name_for_a_feature_finds_the_states_name_for_it(self):
        """``precipitation_3d`` in the graph, ``rainfall_3d`` in the state."""
        agent = CMFBEAgent()
        result = agent.act(
            {"rainfall_3d": 52.0},  # the agent's own callers' spelling
            graph_context(node("precipitation_3d", 49.1)),
        )
        self.assertEqual(len(result["threshold_breaches"]), 1)
        self.assertEqual(result["threshold_breaches"][0]["factor"], "precipitation_3d")

    def test_a_feature_the_state_does_not_carry_is_not_a_breach(self):
        """Missing data is not a reading of zero, and must not become a breach."""
        agent = CMFBEAgent()
        result = agent.act(
            {"turbidity": 20.0},
            graph_context(node("precipitation_3d", 49.1), node("wind_speed", 1.3, unit="m/s")),
        )
        self.assertEqual(result["threshold_breaches"], [])

    def test_a_node_without_a_level_is_not_treated_as_zero(self):
        # 0.0 would make every measured value a breach — the worst possible
        # reading of a node whose split did not converge.
        agent = CMFBEAgent()
        result = agent.act(
            {"precipitation_3d": 5.0},
            graph_context(node("precipitation_3d", None)),
        )
        self.assertEqual(result["threshold_breaches"], [])
        self.assertEqual(result["thresholds"], {})

    def test_the_stale_local_snapshot_is_never_consulted(self):
        """The snapshot beside the agent disagrees with the platform, so it is not read.

        ``agent/outputs/thresholds/cmfbe_threshold_summary.csv`` is a copy of
        the export that has since gone stale: 4 of its 10 levels differ from the
        platform's, ``wind_speed`` by a factor of 2.7. A fallback to it would be
        the original bug with better manners — the same screening against levels
        nobody else uses, now impossible to notice because the agent would be
        reading a file rather than a literal. So this test plants a file at the
        configured path with a distinctive level and asserts the agent ignores
        it: a level the agent was not sent is a level it does not have.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            planted = Path(tmp) / "cmfbe_threshold_summary.csv"
            planted.write_text(
                "scope,context,feature,feature_label,unit,response,n,status,threshold\n"
                "global_test_set,all,precipitation_3d,3-day rain,mm,net_process_response,92,ok,0.001\n",
                encoding="utf-8",
            )
            agent = CMFBEAgent()
            agent.config["threshold_summary_path"] = str(planted)

            result = agent.act({"precipitation_3d": 52.0})
            self.assertEqual(result["threshold_source"], "unavailable")
            self.assertEqual(result["thresholds"], {})
            # 0.001 would have made this a breach. It is not one, because that
            # level was never sent.
            self.assertEqual(result["threshold_breaches"], [])

    def test_with_neither_it_reports_unavailable_rather_than_guessing(self):
        agent = CMFBEAgent()
        agent.threshold_summary = "/nonexistent/thresholds.csv"
        result = agent.act({"precipitation_3d": 999.0}, graph_context(available=False))
        self.assertEqual(result["threshold_source"], "unavailable")
        self.assertEqual(result["thresholds"], {})
        # A missing threshold is not a licence to warn about everything.
        self.assertEqual(result["threshold_breaches"], [])

    def test_a_non_finite_level_cannot_turn_the_screening_off(self):
        """``inf`` is never exceeded and ``nan`` never compares.

        Either would look like a screen that ran and found nothing, which is the
        failure this whole section exists to stop being invisible.
        """
        for bad in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(threshold=bad):
                agent = CMFBEAgent()
                result = agent.act(
                    {"precipitation_3d": 999.0},
                    graph_context(node("precipitation_3d", bad)),
                )
                self.assertEqual(result["thresholds"], {}, bad)
                self.assertEqual(result["threshold_breaches"], [])

    def test_the_rule_based_fallback_uses_the_graphs_thresholds_too(self):
        """Degrading to rules changes where the *process* numbers come from.

        It does not change where the *thresholds* come from: a rule-based run
        still screens against the platform's levels, and both fields say which
        is which.
        """
        agent = CMFBEAgent()
        agent.runner.checkpoint_path = Path("/nonexistent/model.pt")
        result = agent.act({"precipitation_3d": 52.0}, graph_context(node("precipitation_3d", 49.1)))
        self.assertEqual(result["inference_source"], "fallback_rules")
        self.assertEqual(result["threshold_source"], "knowledge_graph")
        self.assertEqual(result["threshold_breaches"][0]["threshold"], 49.1)

    def test_health_does_not_claim_a_threshold_capability(self):
        """Whether this agent screens against thresholds is a per-request fact.

        It depends on whether the platform sent the graph, which a health check
        cannot know. Reading the stale local snapshot here would report a
        capability the agent does not have — the same class of signal that
        called a checkpoint-less agent ``ready``.
        """
        health = CMFBEAgent().health()
        self.assertEqual(
            [key for key in health if "threshold" in key],
            [],
            health,
        )


if __name__ == "__main__":
    unittest.main()
