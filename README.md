# WaterExpert

`WaterExpert` is the cleaned handoff repository for the water clarity diagnosis prototype. It contains the runnable MSCIM and CMFBE-ST-GCN prototype code, the minimum data needed to reproduce the current single-station enhanced run, key model outputs, diagnosis reports, and threshold analysis results.

## 1. What Is Included

- `src/water_ai/`: model and data-processing package.
- `scripts/run_full_pipeline.py`: trains MSCIM, MSCIM-NoKG, CMFBE-ST-GCN, baselines, and exports metrics/diagnosis.
- `scripts/analyze_cmfbe_thresholds.py`: estimates empirical nonlinear/tipping thresholds from CMFBE-ST-GCN test outputs.
- `scripts/export_mscim_driver_overview.py`: exports the MSCIM turbidity-driver overview figure and tables.
- `scripts/plot_cmfbe_process_decomposition.py`: exports the CMFBE source/sink process decomposition figure.
- `configs/prototype_repo.yaml`: portable config using relative repository paths.
- `data/raw/`: minimal raw inputs for the current Wusongkou enhanced prototype.
- `data/knowledge_graph/`: lightweight GraphRAG relationship artifact used as knowledge prior.
- `data/full_station_database/`: processed all-station database tables for collaborator reference.
- `outputs/`: current trained models, predictions, metrics, diagnosis, physics note, plots, and threshold outputs.
- `docs/`: project explanation, reporting notes, and single-day examples for MSCIM and CMFBE-ST-GCN.

## 2. Current Scope

The current runnable model is a single-station enhanced prototype:

- Target water-quality station: Wusongkou / 吴淞口.
- Weather station matched to target: Baoshan / 宝山.
- Hydrodynamic reference stations: Songpu Bridge / 松浦大桥 and Huangdu / 黄渡.
- Training-ready multimodal overlap: 891 days.
- Test window used in current CMFBE threshold analysis: 2024-09-07 to 2024-12-31, 92 days.

The full-station database is included as a database foundation, but the current enhanced model is not yet a 20-station joint hydrodynamic model.

## 3. Main Results

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

## 4. Threshold Output

The CMFBE-ST-GCN threshold analysis estimates empirical nonlinear response thresholds under current data/model conditions. Current strongest empirical thresholds include:

| Factor | Empirical Threshold | Unit | Interpretation |
| --- | ---: | --- | --- |
| 3-day cumulative precipitation | 35.9 | mm | Above this level, net turbidity response tends to increase. |
| 7-day cumulative precipitation | 141.6 | mm | Sustained rainfall background is associated with stronger positive turbidity response. |
| Flushing potential | 3.646 | proxy | Above this level, clearing/export processes strengthen. |
| Huangdu absolute flow | 22.9 | m3/s | Hydrodynamic context changes response regime. |

These are empirical thresholds from the current Wusongkou daily prototype, not calibrated physical critical shear-stress thresholds from a 2D hydrodynamic solver.

## 5. Setup

```powershell
cd G:\AI4S\WaterExpert
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `torch` installation is slow or GPU-specific, install the appropriate PyTorch build first from the official PyTorch instructions, then run `pip install -r requirements.txt`.

## 6. Reproduce Current Pipeline

```powershell
cd G:\AI4S\WaterExpert
python scripts\run_full_pipeline.py --config configs\prototype_repo.yaml
python scripts\plot_cmfbe_process_decomposition.py
python scripts\export_mscim_driver_overview.py
python scripts\analyze_cmfbe_thresholds.py
```

The scripts write outputs to `outputs/`.

## 7. What Is Not Included

The original workspace contained several very large or non-essential folders. They are intentionally excluded from this repository:

- Full `rag_project` embedding/LanceDB artifacts.
- Patent/report crawler raw HTML/PDF bulk folders.
- Historical experiment snapshots `outputs_h3`, `outputs_h7`, and large ad-hoc zip archives.
- PPT working copies.

## 8. Current Technical Boundaries

- MSCIM currently supports prediction and factor diagnosis; the boundary-detection head is reserved but not supervised by raster/UAV labels yet.
- CMFBE-ST-GCN currently uses an explicit daily source-sink mechanism surrogate; it is not yet a calibrated 2D PDE/PINN solver.
- Sobol sensitivity, formal counterfactual intervention, and spatial threshold maps are next-stage work once more spatial hydrodynamic, sediment, algae, and intervention data are available.
