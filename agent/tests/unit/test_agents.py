import unittest

from water_ai.agents import (
    MSCIMAgent,
    CMFBEAgent,
    KnowledgeBaseAgent,
    AquaTurbGPTAgent,
    RLTGRRAgent,
    SafetyAgent,
)


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


if __name__ == "__main__":
    unittest.main()
