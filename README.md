# WaterExpert

Clean handoff repository for the water clarity diagnosis prototype. The repo contains the runnable MSCIM and CMFBE-ST-GCN prototype, the minimum data needed to reproduce the current Wusongkou single-station enhanced run, current outputs, and handoff notes for the next agent-model stage.

## Repository Contents

- `src/water_ai/`: model, data-processing, physics-surrogate, and diagnosis package.
- `scripts/run_full_pipeline.py`: trains MSCIM, MSCIM-NoKG, CMFBE-ST-GCN, baselines, and exports metrics, predictions, diagnosis, plots, and checkpoints.
- `scripts/analyze_cmfbe_thresholds.py`: estimates empirical nonlinear response thresholds from current CMFBE-ST-GCN test outputs.
- `scripts/export_mscim_driver_overview.py`: exports the MSCIM turbidity-driver overview figure and top-driver tables.
- `scripts/plot_cmfbe_process_decomposition.py`: exports the CMFBE source/sink process decomposition figure and summary.
- `scripts/preprocess_shanghai_hydrodynamics.py`: optional standalone hydrodynamics preprocessing utility.
- `configs/prototype_repo.yaml`: primary portable config using repository-relative paths.
- `configs/prototype.yaml`: portable alias for the same runnable prototype defaults.
- `data/raw/`: minimal raw inputs for the current Wusongkou enhanced prototype.
- `data/knowledge_graph/`: lightweight GraphRAG relationship artifact used as the knowledge prior.
- `data/full_station_database/`: processed all-station database tables for collaborator reference.
- `outputs/`: current trained checkpoints, predictions, metrics, diagnosis, physics notes, plots, and threshold reports.
- `docs/`: reporting notes plus `HANDOFF_FOR_AGENT_MODEL.md` for collaborator onboarding.

## Current Scope

The current runnable model is a Wusongkou single-station enhanced prototype.

| Item | Current Value |
| --- | --- |
| Target station | Wusongkou / 吴淞口 |
| Matched weather station | Baoshan / 宝山 |
| Hydrodynamic references | Songpu Bridge / 松浦大桥; Huangdu / 黄渡 |
| Training-ready multimodal overlap | 891 daily rows |
| Current threshold test window | 2024-09-07 to 2024-12-31, 92 days |

The full-station database is included as a data foundation, but the current enhanced model is not yet a 20-station joint hydrodynamic model.

## Main Results

Current test-set performance:

| Model | Turbidity R2 | Clearness Proxy R2 |
| --- | ---: | ---: |
| MSCIM | 0.7812 | 0.7434 |
| MSCIM-NoKG | 0.7395 | 0.6668 |
| CMFBE-ST-GCN | 0.7386 | 0.7097 |
| Persistence baseline | 0.6881 | 0.6523 |

Key outputs:

- MSCIM driver figure: `outputs/plots/mscim_turbidity_driver_overview_20260419.png`
- MSCIM diagnosis tables: `outputs/diagnosis/`
- CMFBE process figure: `outputs/plots/cmfbe_process_decomposition.png`
- CMFBE threshold report: `outputs/thresholds/cmfbe_threshold_report.md`
- CMFBE threshold plot: `outputs/plots/cmfbe_threshold_response_20260430.png`
- Model comparison: `outputs/metrics/model_comparison.csv`
- Trained checkpoints: `outputs/models/`
- Pipeline run summary: `outputs/run_summary.md`

## Threshold Output

The CMFBE-ST-GCN threshold analysis estimates empirical nonlinear response thresholds under current data/model conditions. These are empirical thresholds from the Wusongkou daily prototype, not calibrated physical critical shear-stress thresholds from a 2D hydrodynamic solver.

| Factor | Empirical Threshold | Unit | Interpretation |
| --- | ---: | --- | --- |
| 3-day cumulative precipitation | 35.9 | mm | Above this level, net turbidity response tends to increase. |
| 7-day cumulative precipitation | 141.6 | mm | Sustained rainfall background is associated with stronger positive turbidity response. |
| Flushing potential | 3.646 | proxy | Above this level, clearing/export processes strengthen. |
| Huangdu absolute flow | 22.9 | m3/s | Hydrodynamic context changes response regime. |

## Setup

```powershell
git clone https://github.com/SSSuperfriendly/WaterExpert.git
cd WaterExpert
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `torch` installation is slow or GPU-specific, install the appropriate PyTorch build first from the official PyTorch instructions, then run `pip install -r requirements.txt`.

## Reproduce

```powershell
python scripts\run_full_pipeline.py
python scripts\plot_cmfbe_process_decomposition.py
python scripts\export_mscim_driver_overview.py
python scripts\analyze_cmfbe_thresholds.py
```

All active scripts use repository-relative paths. Outputs are written to `outputs/`.

## Collaborator Acceptance Checklist

1. Clone the repository and install `requirements.txt`.
2. Run `python -m compileall src scripts`.
3. Run `python scripts\analyze_cmfbe_thresholds.py` to confirm the committed predictions and threshold outputs are readable.
4. Run `python scripts\run_full_pipeline.py` if retraining from the included raw inputs is required.
5. Read `docs/HANDOFF_FOR_AGENT_MODEL.md` before extending this into an agent model.

## Technical Boundaries

- MSCIM currently supports prediction and factor diagnosis; the boundary-detection head is reserved but not supervised by raster/UAV labels yet.
- CMFBE-ST-GCN currently uses an explicit daily source-sink mechanism surrogate; it is not yet a calibrated 2D PDE/PINN solver.
- Sobol sensitivity, formal counterfactual intervention, and spatial threshold maps are next-stage work once more spatial hydrodynamic, sediment, algae, and intervention data are available.

## Excluded From This Repo

The original workspace had crawler artifacts, full GraphRAG/LanceDB embeddings, historical prototype folders, PPT working copies, ad-hoc zip archives, and reference PDFs. They were intentionally excluded from the handoff repository because the current reproducible model path only depends on the files above.
