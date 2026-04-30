# WaterExpert Pipeline Run Summary

## 1. Completed Outputs

- Built the Wusongkou daily multimodal dataset for MSCIM and CMFBE-ST-GCN prototype training.
- Converted the lightweight GraphRAG relationship table into feature-graph priors.
- Trained `MSCIM`, `MSCIM-NoKG`, `CMFBE-ST-GCN`, and window baselines.
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
    "turbidity_r2": 0.7812,
    "clearness_r2": 0.7434,
    "turbidity_rmse": 25.1064,
    "clearness_rmse": 0.0382
  },
  "mscim_no_kg": {
    "turbidity_r2": 0.7395,
    "clearness_r2": 0.6668,
    "turbidity_rmse": 27.3918,
    "clearness_rmse": 0.0436
  },
  "cmfbe_stgcn": {
    "turbidity_r2": 0.7386,
    "clearness_r2": 0.7097,
    "turbidity_rmse": 27.4386,
    "clearness_rmse": 0.0407
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

- cmfbe_stgcn: tn (0.216), dayofyear_sin (0.099), huangdu_water_level_m_1d_diff (0.027), mixing_proxy (0.023), huangdu_water_level_m (0.019)
- mscim: huangdu_water_level_m (0.036), songpu_flow_rise_flag (0.036), songpu_flow_m3s_1d_diff (0.035), tn (0.028), huangdu_flow_m3s_7d_mean (0.025)
- mscim_no_kg: conductivity (0.144), huangdu_water_level_m_3d_mean (0.086), tn (0.083), huangdu_water_level_m (0.068), huangdu_flow_m3s_1d_diff (0.029)

## 6. Current Boundaries

- The boundary-detection head is reserved but not supervised by raster or UAV labels yet.
- The current graph is a single-station feature graph, not a multi-section river-network graph.
- The physics component is a runnable source-sink surrogate, not a calibrated 2D hydrodynamic solver.
