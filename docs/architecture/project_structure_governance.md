# Project Structure Governance

## Target Layout

```text
WaterExpert/
+-- backend/app/                # API, state, report, and job orchestration
+-- frontend/                   # Static UI
+-- src/water_ai/               # Reusable research and algorithm core
+-- scripts/
|   +-- pipeline/               # Full runtime entrypoints
|   +-- analysis/               # Threshold/sensitivity/decomposition analysis
|   +-- exports/                # Agent/report/export assembly
|   +-- boundary/               # Boundary-label tooling
|   '-- preprocess/             # Upstream preprocessing
+-- docs/
|   +-- architecture/           # System structure and interfaces
|   +-- specs/                  # Product/software requirements
|   +-- handoffs/               # Research-to-software and agent handoffs
|   +-- reviews/                # Engineering review records
|   +-- design/                 # MVP/product design notes
|   '-- internal/               # Tooling or contributor-local notes
+-- data/                       # Raw and reference data
+-- outputs/                    # Committed baseline artifacts
+-- var/                        # Non-committed software runtime state
'-- tests/                      # Software regression coverage
```

## Why This Split

- `src/water_ai/` stays as the algorithm inheritance boundary. Backend and scripts consume it instead of forking logic.
- `scripts/` is now task-oriented instead of being a flat dumping ground.
- `docs/` is split by purpose so spec, handoff, architecture, and dated reviews stop competing in one directory.
- `var/` isolates volatile application state from reproducible baseline artifacts.

## Dependency Findings

### Acceptable dependencies

- `backend/app/* -> src/water_ai/*` through scripts or direct service logic.
- `scripts/* -> src/water_ai/*` for analysis and export.
- `tests/* -> backend/app/*`, `src/water_ai/*`.

### Current coupling that still deserves future cleanup

1. `backend/app/tasks/job_runner.py` still orchestrates concrete script entrypoints by file path. This is now centralized and categorized, but it is still file-oriented orchestration rather than a callable workflow module.
2. Several export scripts still mutate module-level path globals when `--output-root` changes. They work, but they should be migrated to dataclass-based artifact bundles like the threshold and Sobol scripts.
3. `src/water_ai/interpretability/agent_exports.py` still embeds output-relative artifact strings. That is acceptable while `outputs/` remains the baseline contract, but it should eventually consume a shared artifact-path helper.

## Suspected Clutter And Cleanup Policy

- `var/state/job_runs/*`: runtime history, keep only for debugging or smoke-proof.
- `var/reports/*`: generated HTML exports, safe to prune after verification.
- `__pycache__/` and `*.pyc`: generated clutter, should remain ignored and can be deleted freely.
- `key notes*.pdf`: local-only notes, intentionally ignored and should not be treated as project deliverables.

## Evolution Steps

1. Freeze the layout and update contributor docs first.
2. Keep `src/water_ai/` as the code inheritance anchor; do not duplicate algorithm code into backend.
3. Move more exporter logic from scripts into reusable modules when the APIs stabilize.
4. If job orchestration grows, replace file-path subprocess orchestration with importable workflow functions or a dedicated worker package.
