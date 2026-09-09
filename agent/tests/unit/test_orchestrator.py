import unittest

from water_ai.agents import AquaTurbGPTAgent, RLTGRRAgent, SafetyAgent
from water_ai.orchestrator.coordinator import Orchestrator


class TestOrchestrator(unittest.TestCase):
    def test_orchestrator_executes_agents(self):
        orchestrator = Orchestrator()
        agents = {
            "AquaTurbGPTAgent": AquaTurbGPTAgent(config={"deepseek": {"backend": "local"}}),
            "RLTGRRAgent": RLTGRRAgent(),
            "SafetyAgent": SafetyAgent(),
        }
        result = orchestrator.run(agents, {"rainfall": "high"})
        self.assertIn("reports", result)
        self.assertIn("metrics", result)
        self.assertIn("safe_action", result)


if __name__ == "__main__":
    unittest.main()
