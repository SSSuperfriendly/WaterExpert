# WaterExpert Current Project State

Last updated: 2026-05-30

This file is a handoff document for starting a new AI coding session. Use it together with:

- `CLAUDE-guide.md`: original engineering/design roadmap and deeper implementation intent.
- `QUICKSTART.md`: user-facing runbook and target workflow.
- This file: current source-of-truth for what the repository can actually do right now.

## 1. One-Sentence Status

WaterExpert is now a runnable backend research prototype for multi-agent water quality strategy generation: it can load local water/weather/hydrodynamic datasets, run MSCIM and CMFBE checkpoint-backed inference, call/fallback AquaTurb-GPT planning, execute RL-TGRR actions, safety-screen them, expose a FastAPI strategy API, and generate scenario reports/plots locally.

It is not yet a complete production product: there is no real frontend app, no guaranteed real DeepSeek reasoning unless the user provides `DEEPSEEK_API_KEY`, and some QUICKSTART report/visualization scripts are lightweight local implementations rather than full research-grade deliverables.

## 2. Environment Assumptions

The active environment used for verification is:

```bash
conda run -n water ...
```

The repository root is:

```bash
/home/xchen2/WaterExpert-main
```

Recommended command pattern:

```bash
PYTHONPATH=src conda run -n water python <script>
```

`pytest` is not installed in the `water` environment. Use `unittest` unless dependencies are added:

```bash
PYTHONPATH=src conda run -n water python -m unittest discover -s tests/unit -p 'test_*.py'
```

Current verified test status:

```text
Ran 9 tests
OK
```

## 3. High-Level Architecture

The system is organized as a six-stage multi-agent pipeline:

```text
Input water state
  -> MSCIMAgent checkpoint inference
  -> CMFBEAgent checkpoint inference / process decomposition
  -> KnowledgeBaseAgent technology recommendation
  -> AquaTurbGPTAgent high-level planning via DeepSeek API/local/fallback
  -> RLTGRRAgent low-level action generation using Safe-SAC policy when available
  -> SafetyAgent constraint screening
  -> KPI calculation, feedback, reports, API response
```

Main packages:

- `src/water_ai/agents/`: agent implementations.
- `src/water_ai/models/`: MSCIM and CMFBE-ST-GCN PyTorch model definitions.
- `src/water_ai/data/`: data loading and multimodal dataset construction.
- `src/water_ai/orchestrator/`: multi-agent coordinator, KPI, feedback, reports.
- `src/water_ai/rl/`: RL environment/training/control utilities.
- `src/water_ai/llm/`: DeepSeek client and API/local backends.
- `src/water_ai/api/`: FastAPI app, schemas, routes, job manager.
- `src/water_ai/tech_kb/`: remediation technology knowledge base utilities.
- `src/water_ai/visualization/`: reasoning visualization helper.

## 4. API Backend State

The FastAPI app is in `src/water_ai/api/main.py`.

Start server:

```bash
conda activate water
export DEEPSEEK_API_KEY="sk-your-key"  # optional; without it AquaTurb-GPT falls back
PYTHONPATH=src python scripts/run_api_server.py --host 0.0.0.0 --port 8000
```

Important endpoints:

- `GET /`
- `GET /api/health`
- `GET /api/status`
- `GET /api/scenarios`
- `POST /api/strategy`
- `GET /api/strategy/{job_id}`
- `GET /api/jobs`

Current API route imports were fixed. The API app can be imported and the strategy endpoint has been verified with FastAPI `TestClient`.

Example strategy payload:

```json
{
  "scenario": "s1_external_input",
  "state": {
    "date": "2025-10-31",
    "turbidity": 25.5,
    "flow_rate": 28.5,
    "temperature": 18.2,
    "ph": 7.5,
    "dissolved_oxygen": 8.3,
    "chlorophyll_a": 5.2,
    "rainfall_3d": 45.3,
    "rainfall_7d": 120.5
  },
  "episodes": 1,
  "backend": "api"
}
```

Known API caveat: background jobs are in-memory plus JSON persistence under `outputs/api_jobs`; this is fine for local/demo use, not production multi-worker use.

## 5. Current Agent State

### MSCIMAgent

File: `src/water_ai/agents/mscim_agent.py`

Current behavior:

- Loads `outputs/models/mscim.pt` through `TimeSeriesCheckpointRunner`.
- Runs a true PyTorch checkpoint forward pass when possible.
- Returns:
  - `inference_source: "checkpoint"`
  - predicted turbidity
  - clearness proxy
  - top saliency-driven features as primary drivers
  - model signals such as `delta_gate` and `delta_log_turbidity`
- Falls back to old rule logic only if checkpoint loading/inference fails.

### CMFBEAgent

File: `src/water_ai/agents/cmfbe_agent.py`

Current behavior:

- Loads `outputs/models/cmfbe_stgcn.pt` through `TimeSeriesCheckpointRunner`.
- Runs true PyTorch checkpoint forward pass when possible.
- Returns:
  - `inference_source: "checkpoint"`
  - source/sink process decomposition
  - next-day turbidity prediction
  - physics turbidity prediction
  - velocity/shear/source/sink/fusion signals
- Falls back to old process-rule logic only if checkpoint loading/inference fails.

### Checkpoint Inference Adapter

File: `src/water_ai/agents/checkpoint_inference.py`

Purpose:

- Reconstructs MSCIM or CMFBE-ST-GCN models from checkpoint metadata and state dict.
- Reads checkpoint `feature_columns`, `feature_index`, and `history_days`.
- Estimates feature means/scales from `outputs/intermediate/multimodal_daily_dataset.csv`.
- Converts a single current state into a 21-day synthetic history window for model inference.

Important caveat:

The original checkpoint does not save the training `StandardScaler`, so the adapter re-estimates train-period mean/std from the local intermediate dataset. This is an engineering approximation, but it now performs real model forward inference instead of mock rules.

### KnowledgeBaseAgent

File: `src/water_ai/agents/kb_agent.py`

Current behavior:

- Loads seed knowledge from `data/tech_knowledge_base/tech_quadruples.jsonl`.
- Provides scenario-specific remediation recommendations.
- The knowledge base exists but is small.

### AquaTurbGPTAgent

File: `src/water_ai/agents/aquaturb_gpt_agent.py`

Current behavior:

- Builds a Chinese strategy prompt from scenario and diagnosis.
- Uses `DeepSeekClient.generate_with_fallback`.
- If DeepSeek API/local backend fails, returns built-in fallback strategies.
- Can produce reasoning visualization only if backend response includes `reasoning_tokens`.

DeepSeek API key handling was fixed:

- `src/water_ai/llm/backends/api_backend.py` now reads `DEEPSEEK_API_KEY`.
- `src/water_ai/llm/deepseek_client.py` supports both nested and flat API config styles.

Important caveat:

`src/water_ai/llm/backends/local_backend.py` is still a placeholder. It does not call vLLM or a local model.

### RLTGRRAgent

File: `src/water_ai/agents/rl_tgrr_agent.py`

Current behavior:

- Attempts to load Stable-Baselines3 SAC policy from `outputs/policy/checkpoints/latest.zip`.
- If loaded, uses policy with plan guidance.
- If missing/unavailable, falls back to action rules derived from AquaTurb-GPT strategy.

### SafetyAgent

File: `src/water_ai/agents/safety_agent.py`

Current behavior:

- Clips release, aeration, and chemical dosage to configured limits.
- Returns safe action and violations.

## 6. Model Checkpoints

Existing model files:

- `outputs/models/mscim.pt`
- `outputs/models/cmfbe_stgcn.pt`
- `outputs/models/mscim_no_kg.pt`

Checkpoint structure:

```text
model_name
state_dict
meta
```

Important checkpoint metadata:

- Feature count: 56
- History window: 21 days
- Horizon: 1 day
- Feature columns include water quality, weather, hydrodynamic, seasonal, and engineered process features.

The user does not need to inject these `.pt` files; they already exist and are now used by the agents.

## 7. Data Used

### Raw Data

- `data/raw/wusongkou_water_quality_2586.csv`
  - Wusongkou water-quality station data.
- `data/raw/shanghai_weather_daily.csv`
  - Shanghai daily weather data.
- `data/raw/shanghai_hydrodynamics.xls`
  - Hydrodynamic source file.

### Full Station Database

- `data/full_station_database/water_quality_daily_all_stations.csv`
- `data/full_station_database/multimodal_daily_all_stations_with_weather.csv`
- `data/full_station_database/water_quality_daily_all_stations_with_secchi.csv`
- `data/full_station_database/station_catalog.csv`

Current API/closed-loop loader defaults to station `2586`.

### Knowledge Base Data

- `data/tech_knowledge_base/tech_quadruples.jsonl`
- `data/tech_knowledge_base/applicability_tensor.npz`
- `data/tech_knowledge_base/applicability_tensor.metadata.json`

Caveat: the tensor is currently small. It exists and is usable for local tests, but it does not match the larger-scale tensor described aspirationally in QUICKSTART.

### Intermediate Processed Data

- `outputs/intermediate/multimodal_daily_dataset.csv`
- `outputs/intermediate/multimodal_daily_dataset_with_hydrodynamics.csv`
- `outputs/intermediate/multimodal_dataset_summary.json`
- `outputs/intermediate/feature_graph_adjacency.csv`
- `outputs/intermediate/feature_graph_summary.json`
- `outputs/intermediate/pcmci_discovered_edges.csv`

The checkpoint inference adapter uses `outputs/intermediate/multimodal_daily_dataset.csv` to estimate scaler statistics.

## 8. Existing Outputs

Scenario outputs:

- `outputs/scenarios/s1_external_input/report.md`
- `outputs/scenarios/s1_external_input/data.json`
- `outputs/scenarios/s2_internal_release/report.md`
- `outputs/scenarios/s2_internal_release/data.json`
- `outputs/scenarios/s3_algae_bloom/report.md`
- `outputs/scenarios/s3_algae_bloom/data.json`
- `outputs/scenarios/s4_chronic_combo/report.md`
- `outputs/scenarios/s4_chronic_combo/data.json`
- `outputs/scenarios/SUMMARY.md`

Model metrics and predictions:

- `outputs/predictions/predictions.csv`
- `outputs/metrics/metrics.json`
- `outputs/metrics/model_comparison.csv`
- `outputs/metrics/best_model_summary.json`
- `outputs/metrics/knowledge_enhancement_summary.json`

Diagnostics and interpretability:

- `outputs/diagnosis/*`
- `outputs/interpretability/feature_importance.csv`
- `outputs/physics/physics_equations.md`
- `outputs/physics/physics_coefficients.json`

Policy and Pareto:

- `outputs/policy/checkpoints/latest.zip`
- `outputs/policy/checkpoints/final_model.zip`
- `outputs/policy/checkpoints/rl_model_*.zip`
- `outputs/policy/pareto_candidates.csv`
- `outputs/policy/pareto_front.csv`
- `outputs/policy/pareto_summary.md`
- `outputs/plots/pareto_front.png`
- `outputs/plots/pareto_front.html`

## 9. Scripts and Their Current Meaning

Core run scripts:

- `scripts/run_api_server.py`: starts FastAPI backend.
- `scripts/serve.py`: lightweight FastAPI serve wrapper.
- `scripts/run_closed_loop.py`: runs multi-agent closed-loop scenario demo.
- `scripts/run_aquaturb_gpt_smoke.py`: smoke-tests AquaTurb-GPT with `--backend api/local`; API mode falls back without key.

Training/rebuild scripts:

- `scripts/run_full_pipeline.py`: rebuilds multimodal dataset, trains MSCIM/CMFBE prototypes, saves checkpoints and metrics.
- `scripts/train_rl_tgrr.py`: QUICKSTART-compatible RL-TGRR training entrypoint; can run Stable-Baselines3 training or `--stub`.
- `scripts/train_rl_tgrr_complete.py`: fuller Safe-SAC training implementation.
- `scripts/train_tensor_completion.py`: tensor completion utility.
- `scripts/build_tech_kb.py`: builds applicability tensor from seed KB data.

Visualization/report scripts:

- `scripts/plot_pareto_front.py`: real Pareto candidate/front plotting.
- `scripts/plot_scenario_comparison.py`: lightweight scenario KPI comparison.
- `scripts/plot_kpi_radar.py`: lightweight KPI radar chart.
- `scripts/plot_agent_trace.py`: lightweight agent trace chart.
- `scripts/plot_llm_reasoning.py`: lightweight planning trace chart.
- `scripts/export_report_pdf.py`: lightweight PDF report exporter.
- `scripts/plot_cmfbe_process_decomposition.py`: CMFBE process plot.
- `scripts/export_mscim_driver_overview.py`: MSCIM driver overview export.

Data/utility scripts:

- `scripts/preprocess_shanghai_hydrodynamics.py`
- `scripts/analyze_cmfbe_thresholds.py`
- `scripts/validate_input_data.py`
- `scripts/collect_llm_training_data.py`

All scripts named in QUICKSTART currently exist, but several are lightweight local implementations added to make the workflow executable.

## 10. Verified Commands

Run unit tests:

```bash
PYTHONPATH=src conda run -n water python -m unittest discover -s tests/unit -p 'test_*.py'
```

Run one local closed-loop episode:

```bash
PYTHONPATH=src conda run -n water python scripts/run_closed_loop.py --scenario 1 --episodes 1 --backend local
```

Smoke-test AquaTurb-GPT without API key:

```bash
PYTHONPATH=src conda run -n water python scripts/run_aquaturb_gpt_smoke.py --backend local
```

Validate input data:

```bash
PYTHONPATH=src conda run -n water python scripts/validate_input_data.py
```

Generate local plots:

```bash
PYTHONPATH=src conda run -n water python scripts/plot_scenario_comparison.py --scenarios 1 2 3 4 --output outputs/comparison_scenarios.png
PYTHONPATH=src conda run -n water python scripts/plot_kpi_radar.py --scenarios 1 2 3 4 --output outputs/kpi_radar.png
PYTHONPATH=src conda run -n water python scripts/plot_agent_trace.py --scenario 1 --episode 1 --output outputs/agent_trace_s1_ep1.png
PYTHONPATH=src conda run -n water python scripts/plot_llm_reasoning.py --scenario 1 --output outputs/llm_reasoning_s1.png
```

Export local PDF:

```bash
PYTHONPATH=src conda run -n water python scripts/export_report_pdf.py --scenarios 1 2 3 4 --include-reasoning --output final_presentation.pdf
```

Run short RL training smoke without overwriting current policy:

```bash
PYTHONPATH=src conda run -n water python scripts/train_rl_tgrr.py --steps 10 --scenario s1 --save-interval 5 --output-dir /tmp/water_policy_train --device cpu
```

Run longer RL training into project outputs:

```bash
PYTHONPATH=src conda run -n water python scripts/train_rl_tgrr.py --steps 10000 --scenario s1 --save-interval 1000 --log-interval 500 --device cpu
```

## 11. What Has Been Completed Recently

Recent completed work:

1. Fixed FastAPI route imports so API app can load.
2. Fixed DeepSeek API key resolution from `DEEPSEEK_API_KEY`.
3. Made `run_aquaturb_gpt_smoke.py` accept `--backend`.
4. Made `train_rl_tgrr.py` accept QUICKSTART-style training args and call real local Safe-SAC training.
5. Added missing QUICKSTART scripts:
   - `plot_scenario_comparison.py`
   - `plot_kpi_radar.py`
   - `plot_agent_trace.py`
   - `plot_llm_reasoning.py`
   - `export_report_pdf.py`
   - `validate_input_data.py`
   - `collect_llm_training_data.py`
   - `serve.py`
6. Added `src/water_ai/agents/checkpoint_inference.py`.
7. Connected `MSCIMAgent` to `outputs/models/mscim.pt`.
8. Connected `CMFBEAgent` to `outputs/models/cmfbe_stgcn.pt`.
9. Updated report generation so sample input state is displayed correctly.
10. Added tests verifying checkpoint-backed MSCIM/CMFBE inference.

## 12. Current Known Gaps

### No Frontend Yet

There is no frontend project in the repository. No `package.json`, Vite, Next, React, or Vue app is currently present.

For demos, use:

- Swagger UI at `/docs`
- curl
- FastAPI TestClient
- external frontend if the user already has one

### DeepSeek Is Optional But Not Real Without Key

Without `DEEPSEEK_API_KEY`, API backend falls back to built-in strategies. This lets the pipeline run, but it is not real DeepSeek reasoning.

Real DeepSeek requires:

```bash
export DEEPSEEK_API_KEY="sk-..."
```

Local DeepSeek is not implemented yet; `LocalBackend` is still a placeholder.

### Single-State to 21-Day Window Is Approximate

MSCIM/CMFBE were trained on 21-day windows. API/front-end input gives one state. The current adapter repeats/derives a synthetic 21-day window from the single state. This is acceptable for demo integration, but for higher scientific rigor the API should accept/upload recent historical windows.

### Scenario Sampling Needs Improvement

`scripts/run_closed_loop.py --scenario 1` labels the run as S1, but currently selected data rows may not always naturally satisfy S1 trigger conditions. A future improvement should filter `WaterQualityDataLoader` states by scenario type or scenario trigger.

### Knowledge Base Is Small

The KB tensor exists but is small. To match QUICKSTART's more ambitious wording, expand `data/tech_knowledge_base/tech_quadruples.jsonl` and rebuild:

```bash
PYTHONPATH=src conda run -n water python scripts/build_tech_kb.py
```

### Reports Are Demo-Ready, Not Final Evaluation-Grade

The reporting/plot scripts run and create useful artifacts, but some are lightweight summaries. For final formal delivery, generate fresh four-scenario runs, real DeepSeek reasoning artifacts, and stronger metric tables.

## 13. Recommended Next Tasks

Suggested priority order:

1. Improve scenario state selection so each scenario run uses data matching its trigger conditions.
2. Add API support for optional 21-day historical input windows, while keeping single-state fallback.
3. Add a minimal frontend UI for submitting water state and polling strategy jobs.
4. Implement real local DeepSeek/vLLM backend if API-free LLM reasoning is required.
5. Expand remediation knowledge base and rebuild applicability tensor.
6. Run four scenarios with 30 episodes each and regenerate all outputs.
7. Add integration tests for API `/api/strategy` with checkpoint-backed agents.
8. Persist training scaler in future MSCIM/CMFBE checkpoints to avoid re-estimating scaler stats.

## 14. Practical Handoff Prompt For A New AI Session

Use this prompt when opening a new AI coding session:

```text
You are working in /home/xchen2/WaterExpert-main. Read docs/CURRENT_PROJECT_STATE.md first, then QUICKSTART.md and CLAUDE-guide.md only as supporting context. Treat CURRENT_PROJECT_STATE.md as the current source of truth. The project is a Python/FastAPI multi-agent water-quality strategy prototype using conda env water. MSCIMAgent and CMFBEAgent now use checkpoint-backed PyTorch inference via src/water_ai/agents/checkpoint_inference.py. DeepSeek API is optional and falls back without DEEPSEEK_API_KEY. There is no frontend yet. Before changing behavior, run or preserve: PYTHONPATH=src conda run -n water python -m unittest discover -s tests/unit -p 'test_*.py'. Avoid assuming QUICKSTART claims are all fully production-grade; many scripts are lightweight local implementations.
```

