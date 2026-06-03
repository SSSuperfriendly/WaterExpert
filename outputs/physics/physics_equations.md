# CMFBE-ST-GCN Physics Note

## 1. Reference mechanism equations

### 2D shallow-water momentum / continuity

`dH/dt + d(Hu)/dx + d(Hv)/dy = q`

`d(Hu)/dt + d(Hu^2)/dx + d(Huv)/dy = -gH dZ/dx - tau_bx / rho + F_x`

`d(Hv)/dt + d(Huv)/dx + d(Hv^2)/dy = -gH dZ/dy - tau_by / rho + F_y`

### Suspended sediment transport

`d(HS)/dt + d(HuS)/dx + d(HvS)/dy = d/dx(H D_s dS/dx) + d/dy(H D_s dS/dy) + E - D`

### Krone-type deposition

`D ~ w_s * C * max(0, 1 - tau_b / tau_cd)`

### Eco-dynamics / phytoplankton growth

`dB/dt = mu_max * f(T) * f(I) * min(f(N), f(P)) * f(v) * B - loss_terms`

These are the reference mechanism equations that the full research route should eventually calibrate.

## 2. Current explicit-process surrogate

The current runnable prototype still uses a single-station daily surrogate, but it is no longer a simple linear source/sink sum. It now decomposes the daily log-turbidity change into explicit process terms:

### 2.1 Velocity and shear proxies

`u* = [a_q log(1 + Q_songpu) + a_h log(1 + Q_huangdu)] / [1 + a_d log(1 + H_songpu)]`

`tau* = a_tau u*^2 + a_w log(1 + wind_speed) + a_hs log(1 + |dH_songpu/dt|)`

### 2.2 Source terms

`R_runoff = k_r [log(1 + runoff_sediment_pulse) + 0.35 log(1 + precipitation_3d) + 0.25 log(1 + Q_huangdu)]`

`R_erosion = k_e softplus(tau* - tau_ce) (1 + 0.5 reverse + 0.25 rise)`

`R_tide = k_t [log(1 + tidal_pumping) + 0.3 log(1 + |flow_level_coupling|)]`

`R_bloom = k_b f_T(T) f_I(light) min(f_N(N), f_P(P)) f_v(u*)`

### 2.3 Sink terms

`S_dep = k_d A_sed sigmoid(4 (tau_cd - tau*) / w_v) (1 + beta_floc) (1 + 0.25 log(1 + settling_index))`

`S_flush = k_f A_sed u* log(1 + flushing_potential)`

`S_pur = k_p A_sed f_DO(DO) log(1 + self_purification_index)`

### 2.4 Daily physics balance

`log(1 + T_{t+1}) = clamp(log(1 + T_t) + R_runoff + R_erosion + R_tide + R_bloom - S_dep - S_flush - S_pur, 0)`

`Clearness_t+1 = 1 - (log(1 + Turbidity_t+1) - log_turbidity_min) / (log_turbidity_max - log_turbidity_min)`

The final prediction blends the data-driven branch and the physics-guided branch with fusion ratio `0.665`.

## 3. Learned mechanism parameters

```json
{
  "velocity_flow_scale": 0.197212,
  "velocity_aux_flow_scale": 0.066364,
  "velocity_depth_scale": 0.320219,
  "shear_flow_scale": 0.222890,
  "shear_wind_scale": 0.070732,
  "shear_stage_scale": 0.061860,
  "erosion_threshold": 0.822043,
  "deposition_threshold": 1.270512,
  "erosion_coeff": 0.159725,
  "runoff_coeff": 0.169333,
  "tidal_coeff": 0.124106,
  "bloom_coeff": 0.090637,
  "deposition_coeff": 0.203658,
  "flushing_coeff": 0.240864,
  "purification_coeff": 0.117375,
  "floc_coeff": 0.249455,
  "temp_optimum": 21.968786,
  "temp_width": 6.910357,
  "n_half_sat": 1.064973,
  "p_half_sat": 0.054007,
  "light_threshold": 0.494149,
  "light_sharpness": 3.991783,
  "flow_optimum": 0.882119,
  "flow_width": 0.424253,
  "do_midpoint": 5.874218,
  "do_sharpness": 0.774543,
  "fusion_ratio": 0.665250
}
```

## 4. Scope statement

- Current data scope: single-station multimodal daily prototype
- Boundary head: reserved only, no raster training data available
- Spatial graph statement: implemented as a feature factor graph because only one numeric water-quality station is currently available
- Current physics stage: explicit process surrogate on daily single-station data, not a calibrated 2D PDE solver
