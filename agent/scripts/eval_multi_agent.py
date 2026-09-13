from water_ai.agents import AquaTurbGPTAgent, RLTGRRAgent, SafetyAgent
from water_ai.orchestrator.coordinator import Orchestrator


def main() -> None:
    orchestrator = Orchestrator()
    agents = {
        "AquaTurbGPTAgent": AquaTurbGPTAgent(config={"deepseek": {"backend": "local"}}),
        "RLTGRRAgent": RLTGRRAgent(),
        "SafetyAgent": SafetyAgent(),
    }
    state = {"rainfall": "high", "sediment_release": "high", "chlorophyll": "high", "baseline_turbidity": "elevated"}
    print(orchestrator.run(agents, state))


if __name__ == "__main__":
    main()
