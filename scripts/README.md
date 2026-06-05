# Scripts Layout

- `pipeline/`: full end-to-end runtime entrypoints.
- `analysis/`: threshold, sensitivity, decomposition, and other post-run analysis.
- `exports/`: agent/context/report-oriented artifact exporters.
- `boundary/`: boundary-label template generation and raster proxy labeling.
- `preprocess/`: upstream preprocessing jobs such as hydrodynamics reshaping.

All scripts remain repository-relative and write to `outputs/` unless an explicit `--output-root` override is provided.
