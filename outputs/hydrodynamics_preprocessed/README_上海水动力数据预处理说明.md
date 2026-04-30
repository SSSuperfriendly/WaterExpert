# Shanghai Hydrodynamics Preprocessing

## Source

- Raw file: `data/raw/shanghai_hydrodynamics.xls`
- Script: `scripts/preprocess_shanghai_hydrodynamics.py`

The source workbook contains daily flow and water-level sheets for Huangdu and Songpu Bridge. The available date range is `2022-01-01` to `2024-12-31`.

## Generated Files

1. `outputs/hydrodynamics_preprocessed/shanghai_hydrodynamics_daily_long.csv`
2. `outputs/hydrodynamics_preprocessed/shanghai_hydrodynamics_daily_wide.csv`
3. `outputs/hydrodynamics_preprocessed/summary.json`

## Current Summary

- Long table rows: `4384`
- Wide table rows: `1096`
- Date range: `2022-01-01` to `2024-12-31`
- Primary hydrodynamic reference for the current Wusongkou model: Songpu Bridge
- Auxiliary hydrodynamic reference: Huangdu

## Modeling Notes

- Negative flow values are retained because they may represent backflow, tidal reversal, or reverse hydraulic influence.
- The wide table keeps raw signed flow, absolute flow, reverse flags, rolling means, water-level differences, and flow-level coupling features.
- All joins use `date` as the daily key.
- The current merged training table is `outputs/intermediate/multimodal_daily_dataset_with_hydrodynamics.csv`.
