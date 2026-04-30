# Workspace Cleanup 2026-04-30

## Decision Rule

Keep `G:\AI4S\WaterExpert` as the only active handoff workspace. Delete or exclude everything outside it when the content is an old prototype, duplicate source, generated cache, crawler/RAG artifact, PPT working copy, zip archive, or reference material not required for the reproducible model path.

## High-Confidence Deletion Targets

| Target | Reason |
| --- | --- |
| `AIforScience/` | Old crawler/raw-material workspace; not needed by runnable WaterExpert pipeline. |
| `rag_project/` | Full GraphRAG and LanceDB artifacts; the required `create_final_relationships.parquet` is copied into `data/knowledge_graph/`. |
| `mscim_cmfbe_prototype/` | Superseded prototype; code, configs, selected outputs, and data were migrated into `WaterExpert`. |
| `全站水质综合数据库_20260415/` | Historical delivery copy; aggregate processed tables are included under `data/full_station_database/`. |
| `多模态水质综合数据库_20260412/` | Historical single-station database delivery; current runnable inputs and outputs are inside `WaterExpert`. |
| `当前工作文档/` | Working notes already distilled into repository docs; PDF/DOCX working copies are not model dependencies. |
| `机理方程/` | Reference PDFs summarized into docs/physics notes; not required to run or accept the model handoff. |
| `工程案例/` | Case-study DOCX material; not used by current model pipeline. |
| `turbidity/` | Optional NDTI raster experiments are disabled and not part of the current reproducible run. |
| Root CSV/XLS duplicates | Copied into `data/raw/` with portable English filenames. |
| Root PPT/PDF/ZIP/TXT working files | Historical presentation/archive artifacts, not model dependencies. |

## Repository Cleanup

Removed obsolete configs and scripts that kept absolute `G:\AI4S` assumptions:

- `configs/prototype_h3.yaml`
- `configs/prototype_h7.yaml`
- `configs/prototype_ndti_baseline.yaml`
- `scripts/build_all_station_water_quality_database.py`
- `scripts/build_multimodal_database_delivery.py`
- `scripts/generate_mscim_ppt_diagram.py`
- `scripts/generate_polished_model_slides.py`
- `scripts/merge_hydrodynamics_with_multimodal.py`

Kept active scripts use repository-relative paths.
