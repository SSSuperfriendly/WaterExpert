# WaterExpert

`WaterExpert` remains the research runtime repository for the Wusongkou prototype, and on the `software/waterturbidity-app` branch it also carries the product-layer code for `WaterExpert Software`. The repository root itself is now the runtime root for the software stack.

The current release is intended for scientific review and prototype extension. It is not a production water-quality forecasting service and it is not a calibrated two-dimensional hydrodynamic solver.

The current modeling goal is broader than extrapolating existing turbidity values. The prototype is meant to diagnose turbidity evolution, estimate clearness change and self-purification stress, and identify critical driver levels at which the system tends to shift toward rapid turbidity increase or self-purification failure.

The current handoff package also includes an agent-ready scenario triage layer. It groups daily test-window states into empirical forcing regimes such as `external_input`, `internal_release`, `algal_dominant`, and `chronic_composite` so that a downstream collaborator can build reasoning and orchestration tools on top of the current prototype outputs.

This release now also exports a guarded recommendation playbook. It maps the empirical scenarios to reviewable follow-up actions, monitoring targets, and explicit no-overclaim rules so that a downstream agent can draft response suggestions without pretending that a validated RL controller already exists.

The software-facing UI now also includes a demo login page plus goal-aligned pages for home, database query, data upload, preprocessing, visualization, and integrated prediction/diagnosis.

## Repository Scope

- `backend/`: FastAPI service layer for import, prediction jobs, artifact reads, and report export.
- `frontend/`: browser UI for overview, prediction, diagnostics, scenario triage, thresholds, boundary summary, and task state.
- `tests/`: software regression tests for state, job scoping, and API-serving assumptions.
- `src/water_ai/`: data processing, model definitions, physics-surrogate utilities, metrics, and diagnosis helpers.
- `scripts/pipeline/`: full runtime entrypoints.
- `scripts/analysis/`: threshold, sensitivity, and decomposition analysis.
- `scripts/exports/`: agent-facing and reporting artifact exporters.
- `scripts/boundary/`: boundary-label template and raster proxy tooling.
- `scripts/preprocess/`: preprocessing entrypoints.
- `configs/default.yaml`: primary repository-relative configuration.
- `data/raw/`: minimum raw inputs required for the current Wusongkou enhanced run.
- `data/knowledge_graph/`: lightweight relationship artifact used to build feature-graph priors.
- `data/full_station_database/`: processed all-station reference tables.
- `outputs/`: committed baseline outputs, including checkpoints, metrics, predictions, diagnosis tables, plots, and threshold analysis.
- `var/`: non-committed application state, job-scoped runtime outputs, logs, and exported reports.
- `docs/architecture/technical_overview.md`: external-facing technical overview.
- `docs/handoffs/agent_model_handoff.md`: guidance for building an agent layer on top of this repository.

## Current Model Scope

The runnable enhanced model is centered on Wusongkou station 2586.

| Item | Current Value |
| --- | --- |
| Target station | Wusongkou, station 2586 |
| Matched weather station | Baoshan |
| Hydrodynamic reference stations | Songpu Bridge and Huangdu |
| Training-ready multimodal overlap | 891 daily rows |
| Current threshold test window | 2024-09-07 to 2024-12-31, 92 days |

The all-station database is included as a processed data foundation, but the enhanced model run is not yet a full multi-station hydrodynamic model.

## Model Components

- `MSCIM`: primary prediction and diagnosis model for turbidity, clearness proxy, and dominant driver attribution, built around a feature-graph prior plus a position-aware temporal Transformer encoder.
- `MSCIM-NoKG`: ablation model that removes knowledge-graph priors by using an identity adjacency matrix.
- `CMFBE-ST-GCN`: mechanism-aware hybrid prototype that reuses the MSCIM temporal backbone and adds explicit daily source/sink surrogate terms for runoff, resuspension, tidal trapping, biological growth proxy, deposition/flocculation, flushing/export, and self-purification.

CMFBE-ST-GCN is a daily empirical mechanism surrogate. Its process terms improve interpretability, but they should not be interpreted as calibrated physical parameters from a 2D hydrodynamic model, and its current graph is still a single-station feature graph rather than a multi-section river-network graph.

## Baseline Results

Current committed test-set metrics:

| Model | Turbidity R2 | Clearness Proxy R2 |
| --- | ---: | ---: |
| MSCIM | 0.7735 | 0.7380 |
| MSCIM-NoKG | 0.7644 | 0.7448 |
| CMFBE-ST-GCN | 0.7106 | 0.7151 |
| Persistence baseline | 0.6881 | 0.6523 |

Key output locations:

- `outputs/run_summary.md`
- `outputs/metrics/model_comparison.csv`
- `outputs/metrics/metrics.json`
- `outputs/predictions/predictions.csv`
- `outputs/diagnosis/`
- `outputs/plots/test_turbidity.png`
- `outputs/plots/test_clearness.png`
- `outputs/plots/mscim_turbidity_driver_overview_20260419.png`
- `outputs/plots/cmfbe_process_decomposition.png`
- `outputs/thresholds/cmfbe_threshold_report.md`
- `outputs/thresholds/mechanism_parameter_threshold_kg.json`
- `outputs/agent/agent_context.json`
- `outputs/agent/scenario_triage.json`
- `outputs/agent/response_playbook.json`
- `outputs/boundary/boundary_detection_summary.json`
- `outputs/boundary/boundary_label_generation_summary.json`
- `outputs/sensitivity/cmfbe_sobol_indices.csv`
- `outputs/counterfactual/cmfbe_counterfactual_summary.csv`
- `outputs/counterfactual/cmfbe_joint_counterfactual_summary.csv`
- `outputs/counterfactual/cmfbe_sobol_counterfactual_report.md`
- `outputs/agent/cmfbe_mechanism_intervention_digest.json`
- `outputs/diagnosis/scenario_triage_daily.csv`
- `outputs/plots/cmfbe_threshold_response_20260430.png`
- `outputs/models/`

## Empirical Thresholds

`scripts/analysis/analyze_cmfbe_thresholds.py` estimates empirical nonlinear response thresholds from the current CMFBE-ST-GCN test outputs.

| Factor | Empirical Threshold | Unit |
| --- | ---: | --- |
| 3-day cumulative precipitation | 49.1 | mm |
| 7-day cumulative precipitation | 141.6 | mm |
| Flushing potential | 3.646 | proxy |
| Huangdu absolute flow | 22.9 | m3/s |

These thresholds are model/data empirical breakpoints for the current Wusongkou daily prototype. They are not physical critical shear-stress thresholds.

Within this repository, a threshold refers to the empirical critical level at which one or more turbidity-driving factors tend to cause self-purification failure or sharp turbidity increase during water turbidity transport and recovery.

## Scenario Triage Layer

The repository now exports an empirical scenario triage artifact for the `CMFBE-ST-GCN` test window:

- `external_input`: rainfall-runoff dominated turbidity forcing.
- `internal_release`: bed-shear and resuspension dominated turbidity forcing.
- `algal_dominant`: warm, nutrient-sensitive biological turbidity forcing.
- `chronic_composite`: mixed or persistent multi-driver stress with weakened self-purification support.

These labels are deterministic prototype classifications derived from current process outputs, auxiliary risk scores, and empirical threshold exceedance patterns. They are meant for agent reasoning, screening, and structured case retrieval. They are not validated operational incident labels or intervention policies.

## Recommendation Playbook Layer

The repository now exports `outputs/agent/response_playbook.json` as a scenario-conditioned recommendation scaffold for downstream agents.

This artifact:

- links each empirical scenario to a response focus, follow-up monitoring targets, and required missing data;
- provides guarded action templates for draft recommendations;
- records explicit forbidden claims so the agent does not overstate the current evidence.

It is not a trained `RL-TGRR` policy, not a validated restoration controller, and not proof of intervention optimality.

## Boundary Supervision Interface

The repository now includes a supervision-ready boundary-detection pathway for `MSCIM`.

- Boundary labels can be loaded through `configs/default.yaml`.
- A fill-in template is provided at `data/raw/wusongkou_boundary_labels_template.csv`.
- The repository also includes `scripts/boundary/generate_real_raster_boundary_labels.py`, which derives a real raster boundary-change proxy from DLR daily water masks for the Wusongkou AOI and writes `data/raw/wusongkou_boundary_labels.csv`.
- When raster/UAV-derived labels or the committed real-raster proxy labels are supplied, the pipeline trains the existing boundary head and exports `outputs/boundary/boundary_detection_summary.json`.

These labels should be read as a real raster-derived boundary-change proxy for supervision, not as a manually curated governance-zone map.

## Sobol And Counterfactual Prototype

The repository now exports prototype CMFBE sensitivity, one-factor counterfactual, and linked multi-factor intervention artifacts:

- `outputs/sensitivity/cmfbe_sobol_indices.csv`
- `outputs/sensitivity/cmfbe_sobol_indices.json`
- `outputs/counterfactual/cmfbe_counterfactual_summary.csv`
- `outputs/counterfactual/cmfbe_joint_counterfactual_summary.csv`
- `outputs/counterfactual/cmfbe_sobol_counterfactual_report.md`
- `outputs/agent/cmfbe_mechanism_intervention_digest.json`

These outputs are generated from the current learned CMFBE surrogate and are intended to push the mechanism-parameter-threshold line forward. They are not full calibrated hydrodynamic uncertainty analyses or validated intervention-outcome simulations.

## Environment

The repository was last verified with Python 3.12.7. Install the pinned runtime dependencies:

```powershell
python -m venv .ai4s
.\.ai4s\Scripts\python.exe -m pip install -r requirements.txt
```

If a stale `.ai4s` already exists because the repository was moved to a new directory, rebuild it first:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev\rebuild_venv.ps1
```

If PyTorch installation requires a CPU/GPU-specific wheel, install the appropriate PyTorch build first, then run `python -m pip install -r requirements.txt`.

For collaborator-facing setup on the software branch, see `docs/handoffs/environment_reviewer_quickstart.md`.

## Configuration & Encoding Conventions

- **Text encoding**: all tracked text files use UTF-8. `.editorconfig` enforces `charset = utf-8`, `end_of_line = lf`, and trailing-newline/whitespace rules. Backend responses explicitly set `charset=utf-8`. A guard script (`scripts/dev/check_encoding.py`) detects non-UTF-8 files and GBK-mojibake text.
- **Paths**: configuration and paths are repository-relative, resolved through `backend/app/config.py`. No machine-specific or absolute paths are committed.
- **Environment variables** (see `docs/API/software_api_reference.md` for the full list):

| Variable | Purpose | Default |
| --- | --- | --- |
| `WATEREXPERT_RUNTIME_ROOT` / `WATERTURBIDITY_RUNTIME_ROOT` | runtime root for `outputs/` and `data/` | repository root |
| `WATEREXPERT_REALTIME_APPCODE` / `ALIYUN_APPCODE` | realtime API AppCode (required) | — |
| `WATEREXPERT_DEMO_USERNAME` / `WATEREXPERT_DEMO_PASSWORD` | demo login credentials | `2510709` / `AI4S666` |
| `WATEREXPERT_DEMO_DISPLAY_NAME` / `WATEREXPERT_DEMO_ROLE` | demo profile | `AI4S Demo User` / `reviewer` |

## Software Launch

The realtime validation script requires the Aliyun national surface-water API AppCode to be provided through an environment variable (it is no longer read from a committed draft file):

```powershell
$env:WATEREXPERT_REALTIME_APPCODE = "<your-appcode>"
.\.ai4s\Scripts\python.exe scripts\realtime\validate_latest_realtime.py
powershell -ExecutionPolicy Bypass -File .\scripts\dev\start_local.ps1
```

Then open `http://127.0.0.1:8000/`.

To validate a realtime prediction after its next-day observation has become available, rerun the realtime script with the original prediction timestamp:

```powershell
.\.ai4s\Scripts\python.exe scripts\realtime\validate_latest_realtime.py --as-of-time "2026-07-05 13:00:00"
```

When the target observation exists, the prediction page shows `真实成功率`; otherwise it falls back to `估计成功率`.

To avoid launcher path issues after moving the repository between drives, you can also use the repo-managed startup script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev\start_local.ps1
```

The root route now opens the login page first. Default demo credentials are:

- Username: `2510709`
- Password: `AI4S666`

After login, the main navigation is:

- `首页`
- `水质综合数据库`
- `数据上传`
- `数据预处理`
- `数据可视化`
- `透明度预测与致因诊断`

## Reproduce The Baseline

```powershell
python scripts\pipeline\run_full_pipeline.py
python scripts\analysis\plot_cmfbe_process_decomposition.py
python scripts\exports\export_mscim_driver_overview.py
python scripts\analysis\analyze_cmfbe_thresholds.py
python scripts\exports\export_threshold_knowledge_graph.py
python scripts\exports\export_scenario_triage.py
python scripts\exports\export_response_playbook.py
python scripts\exports\export_agent_context.py
python scripts\boundary\create_boundary_label_template.py
python scripts\boundary\generate_real_raster_boundary_labels.py
python scripts\analysis\analyze_cmfbe_sobol_counterfactual.py
```

The scripts use repository-relative paths and write outputs under `outputs/`.

## Acceptance Checklist

1. Install `requirements.txt`.
2. Run `python -m compileall src scripts`.
3. Run `python scripts\analysis\analyze_cmfbe_thresholds.py` to confirm committed predictions and threshold outputs are readable.
4. Run `python scripts\exports\export_scenario_triage.py`, `python scripts\exports\export_response_playbook.py`, and `python scripts\exports\export_agent_context.py` to confirm the agent-facing artifacts can be regenerated.
5. Run `python scripts\pipeline\run_full_pipeline.py` if retraining from included raw inputs is required.
6. Review `docs/architecture/technical_overview.md` and `docs/handoffs/agent_model_handoff.md` before extending the project.

## Known Boundaries

- The current enhanced model is Wusongkou-centered, not a full multi-station hydrodynamic model.
- Boundary detection is only as strong as the available supervision; the current committed labels are real raster-derived AOI boundary-change proxies, not manual governance-zone annotations.
- Spatial threshold maps and calibrated policy-response analysis are not included.
- The exported scenario tags are empirical triage labels for the current prototype, not validated governance decisions or counterfactual intervention outcomes.
- The exported recommendation playbook is an agent reasoning scaffold, not a trained RL policy or validated intervention optimizer.
- The new Sobol and counterfactual outputs are surrogate-level prototypes, not calibrated operational sensitivity or policy-response results.
- The CMFBE process decomposition supports explanation and empirical screening, not physical calibration.
- The current self-purification failure and critical-transition outputs are empirical prototype risks for screening and agent reasoning, not validated operational warning probabilities.
