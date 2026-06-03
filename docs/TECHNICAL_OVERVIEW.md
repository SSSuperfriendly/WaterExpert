# Technical Overview

## Purpose

`WaterExpert` is a runnable water-clarity diagnosis prototype. It combines daily water-quality observations, weather data, hydrodynamic reference data, and lightweight knowledge-graph priors to predict turbidity and a clearness proxy, diagnose likely turbidity drivers, and flag empirical critical-transition risk related to self-purification failure or rapid turbidity increase.

## Current Data Scope

| Item | Current Scope |
| --- | --- |
| Target station | Wusongkou / station 2586 |
| Matched weather station | Baoshan |
| Hydrodynamic references | Songpu Bridge and Huangdu |
| Training-ready overlap | 891 daily rows |
| Current test window | 2024-09-07 to 2024-12-31, 92 days |

The included `data/full_station_database/` tables provide a broader processed station database for reference, but the current enhanced model run is Wusongkou-centered.

## Model Components

### MSCIM

MSCIM is the main prediction and diagnosis model. It uses time-window features, Transformer-style temporal encoding, feature-graph priors, and saliency-style driver scoring to support:

- turbidity prediction;
- clearness proxy prediction;
- empirical critical-transition risk scoring;
- dominant turbidity-driver ranking;
- single-station diagnostic summaries.

### MSCIM-NoKG

MSCIM-NoKG is an ablation model. It keeps the same model structure but replaces the knowledge-prior adjacency with an identity matrix. It is used to estimate the contribution of the knowledge graph.

### CMFBE-ST-GCN

CMFBE-ST-GCN is the mechanism-aware process model. It shares the MSCIM backbone and adds explicit daily source/sink surrogate terms:

- source terms: runoff input, resuspension/erosion, tidal trapping, biological growth proxy;
- sink terms: deposition/flocculation, flushing/export, self-purification;
- physical consistency: daily source-minus-sink balance, sign consistency, and threshold-response regularization.

This is a daily empirical mechanism surrogate, not a calibrated 2D hydrodynamic PDE solver.

## Current Metrics

Current test-set results:

| Model | Turbidity R2 | Clearness Proxy R2 |
| --- | ---: | ---: |
| MSCIM | 0.7812 | 0.7434 |
| MSCIM-NoKG | 0.7395 | 0.6668 |
| CMFBE-ST-GCN | 0.7386 | 0.7097 |
| Persistence baseline | 0.6881 | 0.6523 |

See `outputs/metrics/model_comparison.csv` and `outputs/run_summary.md` for reproducible output summaries.

## Threshold Analysis

`scripts/analyze_cmfbe_thresholds.py` estimates empirical nonlinear response thresholds from the current CMFBE-ST-GCN test outputs. Current strongest threshold candidates include:

| Factor | Empirical Threshold | Unit |
| --- | ---: | --- |
| 3-day cumulative precipitation | 35.9 | mm |
| 7-day cumulative precipitation | 141.6 | mm |
| Flushing potential | 3.646 | proxy |
| Huangdu absolute flow | 22.9 | m3/s |

These values are model/data empirical thresholds. Here, "threshold" means the empirical critical level at which one or more turbidity-driving factors tend to push the system toward self-purification failure or sharp turbidity increase in the current prototype. They should not be described as physical critical shear-stress thresholds.

## Key Outputs

- `outputs/predictions/predictions.csv`
- `outputs/metrics/model_comparison.csv`
- `outputs/diagnosis/`
- `outputs/plots/mscim_turbidity_driver_overview_20260419.png`
- `outputs/plots/cmfbe_process_decomposition.png`
- `outputs/thresholds/cmfbe_threshold_report.md`
- `outputs/thresholds/mechanism_parameter_threshold_kg.json`
- `outputs/plots/cmfbe_threshold_response_20260430.png`
- `outputs/models/`

## Reproduction

```powershell
python scripts\run_full_pipeline.py
python scripts\plot_cmfbe_process_decomposition.py
python scripts\export_mscim_driver_overview.py
python scripts\analyze_cmfbe_thresholds.py
python scripts\export_threshold_knowledge_graph.py
```

## Current Boundaries

- The current enhanced run is single-station-centered, not a full multi-station hydrodynamic model.
- Boundary detection is reserved in the model design but is not trained without raster/UAV labels.
- Spatial threshold maps, Sobol sensitivity, and counterfactual intervention analysis are not included yet.
- CMFBE-ST-GCN is useful for process explanation and empirical threshold screening, but it is not a calibrated 2D hydrodynamic solver.
- The self-purification failure and critical-transition outputs are empirical auxiliary signals for diagnosis and agent reasoning, not physically calibrated risk probabilities.
