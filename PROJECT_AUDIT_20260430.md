# Project Audit 2026-04-30

## Cleanup Decision

The original `G:\AI4S` workspace mixed raw data, crawler outputs, PPT files, model prototypes, database deliveries, reference PDFs, and historical archives. The handoff target is now the clean `WaterExpert` repository only.

The repository keeps reproducible code, portable configs, minimum raw inputs, lightweight knowledge-prior artifacts, current model outputs, processed all-station reference tables, and documentation. Old workspace artifacts are excluded and should not be treated as dependencies.

## Included In Repository

- Core model code: `src/water_ai/`
- Active scripts: `scripts/run_full_pipeline.py`, `scripts/analyze_cmfbe_thresholds.py`, `scripts/export_mscim_driver_overview.py`, `scripts/plot_cmfbe_process_decomposition.py`, `scripts/preprocess_shanghai_hydrodynamics.py`
- Portable configs: `configs/prototype_repo.yaml`, `configs/prototype.yaml`
- Minimal raw inputs for the current Wusongkou prototype: `data/raw/`
- Lightweight knowledge graph relationship artifact: `data/knowledge_graph/create_final_relationships.parquet`
- All-station processed database tables: `data/full_station_database/`
- Current model outputs: `outputs/`
- Portable run summary: `outputs/run_summary.md`
- Handoff documentation: `README.md`, `docs/`, `docs/HANDOFF_FOR_AGENT_MODEL.md`

## Removed From Handoff Scope

- `rag_project/` full GraphRAG artifacts and LanceDB embeddings.
- `AIforScience/` crawler/raw-material folders.
- Historical prototype folder `mscim_cmfbe_prototype/`.
- Historical database delivery folders and zip archives.
- PPT working copies, old standalone root CSV/XLS duplicates, and ad-hoc extracted text.
- Obsolete experiment configs `prototype_h3.yaml`, `prototype_h7.yaml`, and `prototype_ndti_baseline.yaml`.
- PPT/database builder scripts that depended on the old absolute `G:\AI4S` workspace layout.

## Current Reproducible Path

```powershell
python scripts\run_full_pipeline.py
python scripts\plot_cmfbe_process_decomposition.py
python scripts\export_mscim_driver_overview.py
python scripts\analyze_cmfbe_thresholds.py
```

`scripts/run_full_pipeline.py` now defaults to `configs/prototype_repo.yaml`, so a collaborator can run the pipeline from a cloned repository without editing local paths.

## Remaining Gaps

- The current model is a Wusongkou single-station enhanced prototype, not a full 20-station enhanced hydrodynamic model.
- CMFBE-ST-GCN thresholds are empirical daily-model thresholds, not physical thresholds from calibrated 2D hydrodynamics.
- Spatial boundary maps, Sobol sensitivity, and counterfactual threshold maps remain next-stage work.
