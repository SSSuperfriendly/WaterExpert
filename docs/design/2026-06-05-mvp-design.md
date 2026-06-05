# Design: WaterExpert Software Phase-1 Integrated Product

## Problem Statement

`WaterExpert Software` must not treat `WaterExpert` as an external product bridge. The correct direction is to inherit its existing algorithm code, modeling logic, configs, data, and validated outputs into the software repository itself, then continue product development on top of that integrated runtime.

## Core Decision

Use the current `WaterExpert` repository root as the runtime and let the product layer call it internally.

This means:

- algorithm inheritance, not external product docking
- one software product, not two loosely connected products
- product modules should wrap and schedule the internal runtime
- result viewing remains important, but task creation and data management must also exist

## First Product Cut

The current cut should cover the minimum product flow required by `software_spec_from_softcopyright.md`:

1. data management
2. prediction job configuration
3. result comparison
4. diagnosis and scenario interpretation
5. threshold and boundary summaries
6. report export

## Constraints

- Keep current scientific guardrails unchanged.
- Do not rewrite model internals from zero.
- Reuse the already written `water_ai` code and script entrypoints.
- Keep the software B/S shape: backend service plus browser UI.

## Implementation Mapping

- Data layer: internal runtime `data/` + import API + import logs
- Algorithm layer: internal runtime `src/water_ai/` + `scripts/`
- Application layer: `backend/` + `frontend/`

## Product Boundary

Still true after integration:

- single-station Wusongkou prototype
- empirical thresholds, not calibrated 2D physical control limits
- raster-derived proxy boundary labels
- scenario triage and response playbook as guarded analysis artifacts, not validated control policy

## Next Product Steps

1. browser upload and field mapping
2. richer background task control and logs
3. formal role and permission system
4. more complete report templates and task history
