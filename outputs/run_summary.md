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
    "turbidity_r2": 0.7713,
    "clearness_r2": 0.7301,
    "turbidity_rmse": 25.6656,
    "clearness_rmse": 0.0392
  },
  "mscim_no_kg": {
    "turbidity_r2": 0.7368,
    "clearness_r2": 0.715,
    "turbidity_rmse": 27.5365,
    "clearness_rmse": 0.0403
  },
  "cmfbe_stgcn": {
    "turbidity_r2": 0.7037,
    "clearness_r2": 0.7085,
    "turbidity_rmse": 29.2135,
    "clearness_rmse": 0.0408
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

- cmfbe_stgcn: dayofyear_sin (0.208), huangdu_water_level_m (0.126), nutrient_risk_index (0.056), huangdu_water_level_m_1d_diff (0.050), huangdu_flow_level_coupling (0.049)
- mscim: dayofyear_sin (0.120), tn (0.091), conductivity (0.058), huangdu_flow_m3s_1d_diff (0.028), water_temp (0.025)
- mscim_no_kg: songpu_water_level_m_3d_mean (0.136), tn (0.034), huangdu_water_level_m (0.034), dayofyear_cos (0.034), huangdu_flow_m3s_3d_mean (0.028)

## 6. Current Boundaries

- The boundary-detection head is reserved but not supervised by raster or UAV labels yet.
- The current graph is a single-station feature graph, not a multi-section river-network graph.
- The physics component is a runnable source-sink surrogate, not a calibrated 2D hydrodynamic solver.
- The self-purification failure and critical-transition outputs are empirical prototype risks, not physically calibrated failure probabilities.
