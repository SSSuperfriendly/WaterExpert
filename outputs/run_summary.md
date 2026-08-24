# WaterExpert Pipeline Run Summary

## 1. Completed Outputs

- Built the Wusongkou daily multimodal dataset for MSCIM and CMFBE-ST-GCN prototype training.
- Converted the lightweight GraphRAG relationship table into feature-graph priors.
- Trained `MSCIM`, `MSCIM-NoKG`, `CMFBE-ST-GCN`, and window baselines with auxiliary critical-transition risk outputs.
- Exported predictions, metrics, feature importance, turbidity-driver diagnosis, physics notes, plots, and checkpoints.

## 2. Data Scope

- Water-quality station: Wusongkou / station 2586
- Daily merged rows: 891
- Date range: 2022-01-01 to 2024-12-31
- Selected weather station: Baoshan
- Hydrodynamic references: Songpu Bridge and Huangdu
- Trainable feature count: 56

## 3. Data Splits

- Train: 623 rows, 468 windows
- Validation: 134 rows, 113 windows
- Test: 134 rows, 92 windows

## 4. Metrics Snapshot

```json
{
  "mscim": {
    "turbidity_r2": 0.7291,
    "clearness_r2": 0.6937,
    "turbidity_rmse": 27.9327,
    "clearness_rmse": 0.0418
  },
  "mscim_no_kg": {
    "turbidity_r2": 0.5817,
    "clearness_r2": 0.4995,
    "turbidity_rmse": 34.7119,
    "clearness_rmse": 0.0534
  },
  "cmfbe_stgcn": {
    "turbidity_r2": 0.7481,
    "clearness_r2": 0.7016,
    "turbidity_rmse": 26.9379,
    "clearness_rmse": 0.0412
  },
  "ridge_window_baseline": {
    "turbidity_r2": -0.5739,
    "clearness_r2": -1.2943,
    "turbidity_rmse": 67.3339,
    "clearness_rmse": 0.1144
  },
  "persistence_baseline": {
    "turbidity_r2": 0.6881,
    "clearness_r2": 0.6523,
    "turbidity_rmse": 29.9769,
    "clearness_rmse": 0.0445
  }
}
```

## 5. Main Driver Features

- cmfbe_stgcn: songpu_resuspension_potential (0.031), songpu_water_level_m_1d_diff (0.028), humidity (0.026), huangdu_flow_m3s (0.025), huangdu_flow_m3s_abs (0.025)
- mscim: huangdu_flow_m3s_7d_mean (0.024), huangdu_flow_m3s (0.023), wind_speed (0.022), dayofyear_sin (0.022), songpu_flow_m3s_3d_mean (0.021)
- mscim_no_kg: dayofyear_cos (0.024), conductivity_anomaly (0.022), songpu_resuspension_potential (0.021), songpu_flow_m3s_7d_mean (0.021), songpu_flow_m3s_1d_diff (0.021)

## 6. Current Boundaries

- Boundary supervision: 248 labeled days loaded from `G:\AI4S\WaterExpert\data\raw\wusongkou_boundary_labels.csv`.
- The current graph is a single-station feature graph, not a multi-section river-network graph.
- The physics component is a runnable source-sink surrogate, not a calibrated 2D hydrodynamic solver.
- The self-purification failure and critical-transition outputs are empirical prototype risks, not physically calibrated failure probabilities.
