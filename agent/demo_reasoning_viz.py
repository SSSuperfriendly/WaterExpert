#!/usr/bin/env python
"""
Demonstration script for DeepSeek Reasoning Visualization.

This script shows how to enable and visualize DeepSeek reasoning tokens
when an API key is available.

Usage:
    python demo_reasoning_viz.py --scenario s1_external_input
    
Environment:
    Set DEEPSEEK_API_KEY environment variable to enable real API calls
    Without it, the system will use fallback strategies and show the capabilities.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from water_ai.agents.aquaturb_gpt_agent import AquaTurbGPTAgent
from water_ai.visualization.reasoning_viz import ReasoningVisualizer


def demo_reasoning_visualization():
    """Demonstrate the reasoning visualization capability."""
    print("=" * 80)
    print("DeepSeek Reasoning Visualization Demo")
    print("=" * 80)

    # Check for API key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        print("\n✓ DEEPSEEK_API_KEY found - Real API calls will be made")
        backend_mode = "api"
    else:
        print("\n⚠ DEEPSEEK_API_KEY not found - Using fallback/mock mode")
        print("  To see real reasoning tokens, set DEEPSEEK_API_KEY environment variable")
        backend_mode = "fallback"

    # Initialize visualizer
    ReasoningVisualizer(output_dir="outputs/visualization")
    print("✓ Visualization output directory: outputs/visualization/")

    # Initialize agent with API backend
    agent_config = {
        "deepseek": {
            "backend": "api",
            "api": {
                "api_key": api_key or "mock-key",
                "endpoint": "https://api.deepseek.com/chat/completions",
                "model": "deepseek-chat",
                "enable_reasoning": True,
                "max_tokens": 2048,
            }
        }
    }
    agent = AquaTurbGPTAgent(config=agent_config)
    print(f"✓ Agent initialized with {backend_mode} backend")

    # Test scenarios
    scenarios = [
        {
            "key": "s1_external_input",
            "title": "External Input Type (外源输入型)",
            "diagnosis": {
                "primary_drivers": ["Rainfall increase (3-day cumulative >36mm)"],
                "confidence": 0.92,
                "flow_condition": "High flow (>22.9 m³/s)",
                "turbidity": 25.5,
            },
        },
        {
            "key": "s2_internal_release",
            "title": "Internal Release Type (内源释放型)",
            "diagnosis": {
                "primary_drivers": ["Sediment resuspension"],
                "confidence": 0.75,
                "flow_condition": "Normal flow",
                "turbidity": 18.2,
            },
        },
        {
            "key": "s3_algae_bloom",
            "title": "Algae Bloom Type (藻华主导型)",
            "diagnosis": {
                "primary_drivers": ["Algae proliferation (Chl-a > 8 μg/L)"],
                "confidence": 0.85,
                "flow_condition": "Low flow + sufficient sunlight",
                "turbidity": 12.3,
            },
        },
        {
            "key": "s4_chronic_combo",
            "title": "Chronic Combination Type (慢性复合型)",
            "diagnosis": {
                "primary_drivers": ["Multiple long-term factors"],
                "confidence": 0.70,
                "flow_condition": "Baseline conditions",
                "turbidity": 5.8,
            },
        },
    ]

    print(f"\n{'=' * 80}")
    print("Running agent decision-making for all 4 scenarios...")
    print(f"{'=' * 80}\n")

    generated_files = []

    for scenario in scenarios:
        print(f"[{scenario['key']}] {scenario['title']}")

        # Call agent
        planning_input = {
            "scenario": scenario["key"],
            "diagnosis": scenario["diagnosis"],
        }

        result = agent.act(planning_input)

        # Check if reasoning visualization was generated
        strategy = result.get("strategy", {})
        viz_path = strategy.get("reasoning_viz_path")

        if viz_path:
            print(f"  ✓ Reasoning visualization generated: {viz_path}")
            generated_files.append(viz_path)
        else:
            print("  ⚠ No reasoning tokens captured (using fallback strategy)")

        # Show strategy summary
        print(f"  - Confidence: {strategy.get('scenario_confidence', 0):.1%}")
        print(f"  - Actions: {[a.get('action') for a in strategy.get('recommended_actions', [])]}")
        print()

    # Summary
    print(f"{'=' * 80}")
    print("Demonstration Complete")
    print(f"{'=' * 80}")
    print(f"\nBackend Mode: {backend_mode}")
    print(f"Generated Files: {len(generated_files)}")

    if generated_files:
        print("\nGenerated Visualization Files:")
        for f in generated_files:
            print(f"  - {f}")
        print("\nTo view reasoning visualizations, open the HTML files in a browser.")

    print("\n" + "=" * 80)
    print("Next Steps:")
    print("=" * 80)
    print("""
1. Set DEEPSEEK_API_KEY environment variable:
   export DEEPSEEK_API_KEY="sk-..."
   
2. Run the full closed-loop system with reasoning visualization:
   python scripts/run_closed_loop.py --scenario all --episodes 5 --backend api
   
3. Check the generated reports in outputs/scenarios/*/report.md
   The reports will include links to reasoning visualizations if available.
   
4. View reasoning visualizations:
   Open outputs/visualization/reasoning_*.html files in your browser
   
For more information, see QUICKSTART.md section 4.
""")


if __name__ == "__main__":
    demo_reasoning_visualization()
