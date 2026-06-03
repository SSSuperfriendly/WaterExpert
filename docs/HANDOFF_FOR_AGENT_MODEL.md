# Handoff For Agent Model

## Goal

Use `WaterExpert` as the model and data foundation for a water-clarity diagnosis agent. The agent should answer questions about current prototype results, explain MSCIM/CMFBE outputs, surface likely turbidity drivers, and guide next experiments without overstating the current model scope.

The agent should treat the project as a diagnosis and decision-support prototype, not as a narrow next-step turbidity extrapolator. It should be able to reason about turbidity evolution, clearness change, self-purification stress, and threshold-triggered regime shifts.

## What The Agent Can Rely On

- Runnable prototype: `python scripts\run_full_pipeline.py`
- Main config: `configs/prototype_repo.yaml`
- Current prediction table: `outputs/predictions/predictions.csv`
- Current metrics: `outputs/metrics/model_comparison.csv`, `outputs/metrics/metrics.json`
- MSCIM diagnosis: `outputs/diagnosis/`
- CMFBE process decomposition: `outputs/diagnosis/cmfbe_process_decomposition_summary.csv`, `outputs/plots/cmfbe_process_decomposition.png`
- Threshold analysis: `outputs/thresholds/cmfbe_threshold_report.md`, `outputs/thresholds/cmfbe_threshold_summary.csv`
- Threshold knowledge graph: `outputs/thresholds/mechanism_parameter_threshold_kg.json`
- Scenario triage: `outputs/agent/scenario_triage.json`, `outputs/diagnosis/scenario_triage_daily.csv`
- Recommendation playbook: `outputs/agent/response_playbook.json`
- Unified agent context: `outputs/agent/agent_context.json`
- Data foundation: `data/raw/`, `data/full_station_database/`, `data/knowledge_graph/`

## Recommended Agent Capabilities

1. Result Q&A: read metrics, prediction windows, threshold summaries, and diagnosis tables.
2. Driver explanation: summarize which meteorological, hydrodynamic, water-quality, and knowledge-graph factors dominate turbidity changes.
3. Scenario triage: compare rainfall, flow, flushing, and resuspension conditions against empirical thresholds and identify possible self-purification failure or turbidity-surge risk.
4. Scenario retrieval: surface whether the latest state is closer to `external_input`, `internal_release`, `algal_dominant`, or `chronic_composite`, and explain why using the exported evidence fields.
5. Guarded recommendation drafting: use `outputs/agent/response_playbook.json` to draft follow-up monitoring advice and response templates without presenting them as validated intervention policies.
6. Data-gap detection: tell users when a requested spatial, physical, counterfactual, Sobol, or policy-optimization claim is outside the current evidence.
7. Threshold reasoning: retrieve threshold nodes and contextual threshold nodes from the exported mechanism-parameter-threshold knowledge graph.
8. Agent grounding: use `outputs/agent/agent_context.json` as the first-stop summary for metrics, risk snapshot, scenario counts, best-model note, and guardrails.
9. Experiment orchestration: call the active scripts, check generated outputs, and report changed metrics.

## Guardrails

- Do not describe the current thresholds as physical critical thresholds from a calibrated 2D hydrodynamic model.
- Do not describe the current self-purification failure probabilities as operationally calibrated early-warning probabilities.
- Do not describe the current scenario tags as validated intervention classes or governance recommendations.
- Do not describe the current response playbook as RL-TGRR, a trained policy, or an optimal restoration controller.
- Do not claim a 20-station joint hydrodynamic model has been trained; the current enhanced run is Wusongkou-centered.
- Do not claim spatial boundary maps, Sobol indices, or counterfactual threshold maps exist unless new outputs are added.
- Treat `outputs/` as the current reproducible baseline, not as proof of production readiness.

## Suggested Extension Path

1. Wrap `outputs/metrics`, `outputs/diagnosis`, `outputs/thresholds`, `outputs/agent/scenario_triage.json`, and `outputs/agent/response_playbook.json` with retrieval tools for grounded answers.
2. Add a script runner tool that executes the active scripts and checks whether expected files changed.
3. Add a data validator for required raw inputs and config paths before training.
4. Add structured response templates for `metric_summary`, `driver_diagnosis`, `threshold_check`, `scenario_triage`, `response_playbook`, `critical_transition_risk`, and `data_gap`.
5. Use `outputs/thresholds/mechanism_parameter_threshold_kg.json`, `outputs/agent/scenario_triage.json`, `outputs/agent/response_playbook.json`, and `outputs/agent/agent_context.json` as the first structured retrieval artifacts for agent-side reasoning.
6. Add future tools only after new data exists for multi-station hydrodynamics, raster/UAV boundaries, Sobol sensitivity, counterfactual experiments, intervention records, and explicit action-effect observations.
