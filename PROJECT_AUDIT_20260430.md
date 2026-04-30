# Project Audit 2026-04-30

## 1. Cleanup Decision

The original `G:\AI4S` workspace is a mixed working directory containing raw data, crawler outputs, PPT files, model prototypes, database deliveries, and historical archives. For GitHub handoff, the safe approach is not to delete the workspace, but to create a clean repository with only reproducible code, necessary lightweight data, current model outputs, and documentation.

## 2. Included In Repository

- Core model code: `src/water_ai/`
- Training and analysis scripts: `scripts/`
- Portable config: `configs/prototype_repo.yaml`
- Minimal raw inputs for current Wusongkou prototype: `data/raw/`
- Lightweight knowledge graph relationship artifact: `data/knowledge_graph/create_final_relationships.parquet`
- All-station processed database tables: `data/full_station_database/`
- Current model outputs: `outputs/`
- Handoff documentation: `docs/`

## 3. Excluded From Repository

- `rag_project/` full artifacts: too large, especially LanceDB embedding files.
- `AIforScience/` crawler/raw-material folders: not needed for model handoff.
- historical zip archives and PPT working files.
- ad-hoc historical model output snapshots.

## 4. New Work Added

- Added `scripts/analyze_cmfbe_thresholds.py`.
- Added CMFBE threshold outputs under `outputs/thresholds/`.
- Added `outputs/plots/cmfbe_threshold_response_20260430.png`.
- Added portable repository config `configs/prototype_repo.yaml`.
- Updated `requirements.txt` with `tigramite`, `openpyxl`, and `xlrd`.

## 5. Remaining Gaps

- The current model is a Wusongkou single-station enhanced prototype, not a full 20-station enhanced hydrodynamic model.
- CMFBE-ST-GCN thresholds are empirical daily-model thresholds, not physical thresholds from calibrated 2D hydrodynamics.
- Spatial boundary maps, Sobol sensitivity, and counterfactual threshold maps remain next-stage work.
