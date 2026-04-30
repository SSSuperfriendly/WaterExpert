# WaterExpert

`WaterExpert` is a self-contained research handoff repository for a water-clarity diagnosis prototype. It provides runnable code, portable configuration, minimum raw inputs, current model outputs, and concise technical documentation for external collaboration.

The current release is intended for scientific review and prototype extension. It is not a production water-quality forecasting service and it is not a calibrated two-dimensional hydrodynamic solver.

## Repository Scope

- `src/water_ai/`: data processing, model definitions, physics-surrogate utilities, metrics, and diagnosis helpers.
- `scripts/`: executable pipeline and post-analysis scripts.
- `configs/prototype_repo.yaml`: primary repository-relative configuration.
- `configs/prototype.yaml`: equivalent portable default configuration.
- `data/raw/`: minimum raw inputs required for the current Wusongkou enhanced run.
- `data/knowledge_graph/`: lightweight relationship artifact used to build feature-graph priors.
- `data/full_station_database/`: processed all-station reference tables.
- `outputs/`: committed baseline outputs, including checkpoints, metrics, predictions, diagnosis tables, plots, and threshold analysis.
- `docs/TECHNICAL_OVERVIEW.md`: external-facing technical overview.
- `docs/HANDOFF_FOR_AGENT_MODEL.md`: guidance for building an agent layer on top of this repository.

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

- `MSCIM`: primary prediction and diagnosis model for turbidity, clearness proxy, and dominant driver attribution.
- `MSCIM-NoKG`: ablation model that removes knowledge-graph priors by using an identity adjacency matrix.
- `CMFBE-ST-GCN`: mechanism-aware model that adds explicit daily source/sink surrogate terms for runoff, resuspension, tidal trapping, biological growth proxy, deposition/flocculation, flushing/export, and self-purification.

CMFBE-ST-GCN is a daily empirical mechanism surrogate. Its process terms improve interpretability, but they should not be interpreted as calibrated physical parameters from a 2D hydrodynamic model.

## Baseline Results

Current committed test-set metrics:

| Model | Turbidity R2 | Clearness Proxy R2 |
| --- | ---: | ---: |
| MSCIM | 0.7812 | 0.7434 |
| MSCIM-NoKG | 0.7395 | 0.6668 |
| CMFBE-ST-GCN | 0.7386 | 0.7097 |
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
- `outputs/plots/cmfbe_threshold_response_20260430.png`
- `outputs/models/`

## Empirical Thresholds

`scripts/analyze_cmfbe_thresholds.py` estimates empirical nonlinear response thresholds from the current CMFBE-ST-GCN test outputs.

| Factor | Empirical Threshold | Unit |
| --- | ---: | --- |
| 3-day cumulative precipitation | 35.9 | mm |
| 7-day cumulative precipitation | 141.6 | mm |
| Flushing potential | 3.646 | proxy |
| Huangdu absolute flow | 22.9 | m3/s |

These thresholds are model/data empirical breakpoints for the current Wusongkou daily prototype. They are not physical critical shear-stress thresholds.

## Environment

The repository was last verified with Python 3.12.7. Install the pinned runtime dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PyTorch installation requires a CPU/GPU-specific wheel, install the appropriate PyTorch build first, then run `pip install -r requirements.txt`.

## Reproduce The Baseline

```powershell
python scripts\run_full_pipeline.py
python scripts\plot_cmfbe_process_decomposition.py
python scripts\export_mscim_driver_overview.py
python scripts\analyze_cmfbe_thresholds.py
```

The scripts use repository-relative paths and write outputs under `outputs/`.

## Acceptance Checklist

1. Install `requirements.txt`.
2. Run `python -m compileall src scripts`.
3. Run `python scripts\analyze_cmfbe_thresholds.py` to confirm committed predictions and threshold outputs are readable.
4. Run `python scripts\run_full_pipeline.py` if retraining from included raw inputs is required.
5. Review `docs/TECHNICAL_OVERVIEW.md` and `docs/HANDOFF_FOR_AGENT_MODEL.md` before extending the project.

## Known Boundaries

- The current enhanced model is Wusongkou-centered, not a full multi-station hydrodynamic model.
- Boundary detection is reserved in the model design but is not trained without raster or UAV labels.
- Spatial threshold maps, Sobol sensitivity, and counterfactual intervention analysis are not included.
- The CMFBE process decomposition supports explanation and empirical screening, not physical calibration.
