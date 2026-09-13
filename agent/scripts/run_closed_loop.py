"""
End-to-end closed-loop water quality management system.

Orchestrates multi-agent decisions across four scenarios:
- S1: External input (rainfall-driven)
- S2: Internal release (resuspension-driven)
- S3: Algae bloom (biological-driven)
- S4: Chronic combo (multiple factors)

Runs for multiple episodes and generates scenario reports.
"""

import argparse

from water_ai.agents import (
    AquaTurbGPTAgent,
    CMFBEAgent,
    KnowledgeBaseAgent,
    MSCIMAgent,
    RLTGRRAgent,
    SafetyAgent,
)
from water_ai.data.loader import WaterQualityDataLoader
from water_ai.orchestrator.coordinator import Orchestrator
from water_ai.orchestrator.report_generator import ReportGenerator


def main(scenario: str = "1", episodes: int = 10, backend: str = "api") -> None:
    """
    Run closed-loop multi-agent system.

    Args:
        scenario: Scenario number (1-4) or "all"
        episodes: Number of episodes to run
        backend: DeepSeek backend ("api" or "local")
    """
    print("=" * 80)
    print("WaterExpert Multi-Agent Closed-Loop System")
    print("=" * 80)

    # Initialize data loader
    print("\n[1/6] Initializing data loader...")
    try:
        loader = WaterQualityDataLoader(target_station=2586)
        start_date, end_date = loader.get_date_range()
        print(f"     ✓ Data range: {start_date} to {end_date}")
        print(f"     ✓ Total records: {loader.get_total_rows()}")
    except Exception as e:
        print(f"     ✗ Failed to load data: {e}")
        return

    # Initialize agents
    print("\n[2/6] Initializing agents...")
    try:
        agents = {
            "MSCIMAgent": MSCIMAgent(),
            "CMFBEAgent": CMFBEAgent(),
            "KnowledgeBaseAgent": KnowledgeBaseAgent(),
            "AquaTurbGPTAgent": AquaTurbGPTAgent(config={"deepseek": {"backend": backend}}),
            "RLTGRRAgent": RLTGRRAgent(),
            "SafetyAgent": SafetyAgent(),
        }
        print(f"     ✓ Initialized {len(agents)} agents")
        for name in agents:
            print(f"       - {name}")
    except Exception as e:
        print(f"     ✗ Failed to initialize agents: {e}")
        return

    # Initialize orchestrator
    print("\n[3/6] Initializing orchestrator...")
    orchestrator = Orchestrator()
    print("     ✓ Orchestrator ready")

    # Determine scenario list to run
    if scenario == "all":
        scenarios_to_run = ["1", "2", "3", "4"]
    else:
        scenarios_to_run = [scenario]

    all_results = {}

    # Run scenarios
    for scenario_num in scenarios_to_run:
        scenario_key = f"s{scenario_num}_external_input" if scenario_num == "1" else \
                      f"s{scenario_num}_internal_release" if scenario_num == "2" else \
                      f"s{scenario_num}_algae_bloom" if scenario_num == "3" else \
                      f"s{scenario_num}_chronic_combo"

        print(f"\n[4/6] Running scenario {scenario_num} ({scenario_key})...")

        scenario_results = {
            "episodes": [],
            "metrics_summary": {},
            "scenario_type": scenario_key,
        }

        # Run episodes
        for episode in range(episodes):
            print(f"       Episode {episode + 1}/{episodes}...", end=" ")

            try:
                # Get random state from data
                idx = (episode * 10) % (loader.get_total_rows() - 1)
                current_state = loader.get_state_at_index(idx)

                # Run orchestrator for this timestep
                episode_result = orchestrator.run(agents, current_state, scenario_key)

                scenario_results["episodes"].append(episode_result)
                print("✓")

            except Exception as e:
                print(f"✗ ({e})")
                continue

        # Aggregate metrics
        if scenario_results["episodes"]:
            episode_metrics = [ep.get("metrics", {}) for ep in scenario_results["episodes"]]
            
            # Extract reasoning visualization path from first episode if available
            reasoning_viz_path = None
            for episode in scenario_results["episodes"]:
                planning_info = episode.get("planning", {})
                if planning_info and isinstance(planning_info, dict):
                    viz_path = planning_info.get("strategy", {}).get("reasoning_viz_path")
                    if viz_path:
                        reasoning_viz_path = viz_path
                        break
            
            scenario_results["metrics_summary"] = {
                "avg_turbidity_reduction": sum(
                    m.get("turbidity_reduction", 0.0) for m in episode_metrics
                ) / len(episode_metrics),
                "avg_turbidity_reduction_ratio": sum(
                    m.get("turbidity_reduction_ratio", 0.0) for m in episode_metrics
                ) / len(episode_metrics),
                "avg_energy_cost": sum(
                    m.get("energy_cost", 0.0) for m in episode_metrics
                ) / len(episode_metrics),
                "avg_cost_saving_ratio": sum(
                    m.get("cost_saving_ratio", 0.0) for m in episode_metrics
                ) / len(episode_metrics),
                "avg_stability": sum(
                    m.get("stability", 0.0) for m in episode_metrics
                ) / len(episode_metrics),
                "avg_response_time_hours": sum(
                    m.get("response_time_hours", 0.0) for m in episode_metrics
                ) / len(episode_metrics),
                "total_episodes": len(scenario_results["episodes"]),
            }
            
            # Store reasoning visualization path if found
            if reasoning_viz_path:
                scenario_results["reasoning_viz_path"] = reasoning_viz_path

        all_results[scenario_key] = scenario_results

    # Generate reports
    print("\n[5/6] Generating reports...")
    try:
        report_gen = ReportGenerator(output_base="outputs/scenarios")

        for scenario_key, scenario_data in all_results.items():
            report_path = report_gen.generate_scenario_report(
                scenario_key=scenario_key,
                scenario_data=scenario_data,
                agents_info={name: agent.status() for name, agent in agents.items()},
            )
            print(f"     ✓ Report saved: {report_path}")

        # Generate summary report
        summary_path = report_gen.generate_summary_report(all_results)
        print(f"     ✓ Summary report: {summary_path}")

    except Exception as e:
        print(f"     ✗ Failed to generate reports: {e}")
        import traceback
        traceback.print_exc()

    print("\n[6/6] Results summary:")
    for scenario_key, scenario_data in all_results.items():
        metrics = scenario_data.get("metrics_summary", {})
        print(f"\n  {scenario_key}:")
        print(f"    - Episodes run: {metrics.get('total_episodes', 0)}")
        print(f"    - Avg turbidity reduction ratio: {metrics.get('avg_turbidity_reduction_ratio', 0):.2%}")
        print(f"    - Avg turbidity reduction: {metrics.get('avg_turbidity_reduction', 0):.2f} NTU")
        print(f"    - Avg energy cost: ¥{metrics.get('avg_energy_cost', 0):.2f}")
        print(f"    - Avg cost saving: {metrics.get('avg_cost_saving_ratio', 0):.2%}")
        print(f"    - Avg stability: {metrics.get('avg_stability', 0):.2%}")

    print("\n" + "=" * 80)
    print("✓ Closed-loop run completed!")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run WaterExpert closed-loop system")
    parser.add_argument(
        "--scenario",
        type=str,
        default="1",
        choices=["1", "2", "3", "4", "all"],
        help="Scenario to run (1-4 or all)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=10,
        help="Number of episodes per scenario",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="api",
        choices=["api", "local"],
        help="DeepSeek backend (api or local)",
    )

    args = parser.parse_args()
    main(scenario=args.scenario, episodes=args.episodes, backend=args.backend)
