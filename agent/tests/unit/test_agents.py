import unittest

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


if __name__ == "__main__":
    unittest.main()
