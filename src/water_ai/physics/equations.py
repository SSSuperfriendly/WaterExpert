from __future__ import annotations

from pathlib import Path
from typing import Any

from water_ai.utils.io import ensure_dir


def build_physics_markdown(coefficients: dict[str, Any], data_summary: dict[str, Any]) -> str:
    parameters = coefficients.get("parameters", {})
    formulas = coefficients.get("process_formulas", {})

    return f"""# CMFBE-ST-GCN Physics Note

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

`{formulas.get("velocity_proxy", "u* = surrogate(flow, stage)")}`

`{formulas.get("bed_shear_proxy", "tau* = surrogate(u*, wind, stage_change)")}`

### 2.2 Source terms

`{formulas.get("runoff_source", "R_runoff = runoff-driven source")}`

`{formulas.get("erosion_source", "R_erosion = shear-threshold erosion source")}`

`{formulas.get("tidal_source", "R_tide = tidal trapping source")}`

`{formulas.get("bloom_source", "R_bloom = eco-dynamics bloom source")}`

### 2.3 Sink terms

`{formulas.get("krone_deposition_sink", "S_dep = Krone-style deposition sink")}`

`{formulas.get("flushing_sink", "S_flush = advection / flushing sink")}`

`{formulas.get("purification_sink", "S_pur = self-purification sink")}`

### 2.4 Daily physics balance

`{formulas.get("physics_balance", "log(1 + T_t+1) = log(1 + T_t) + sources - sinks")}`

`Clearness_t+1 = 1 - (log(1 + Turbidity_t+1) - log_turbidity_min) / (log_turbidity_max - log_turbidity_min)`

The final prediction blends the data-driven branch and the physics-guided branch with fusion ratio `{coefficients.get("fusion_ratio", 0.0):.3f}`.

## 3. Learned mechanism parameters

```json
{{
  "velocity_flow_scale": {parameters.get("velocity_flow_scale", 0.0):.6f},
  "velocity_aux_flow_scale": {parameters.get("velocity_aux_flow_scale", 0.0):.6f},
  "velocity_depth_scale": {parameters.get("velocity_depth_scale", 0.0):.6f},
  "shear_flow_scale": {parameters.get("shear_flow_scale", 0.0):.6f},
  "shear_wind_scale": {parameters.get("shear_wind_scale", 0.0):.6f},
  "shear_stage_scale": {parameters.get("shear_stage_scale", 0.0):.6f},
  "erosion_threshold": {parameters.get("erosion_threshold", 0.0):.6f},
  "deposition_threshold": {parameters.get("deposition_threshold", 0.0):.6f},
  "erosion_coeff": {parameters.get("erosion_coeff", 0.0):.6f},
  "runoff_coeff": {parameters.get("runoff_coeff", 0.0):.6f},
  "tidal_coeff": {parameters.get("tidal_coeff", 0.0):.6f},
  "bloom_coeff": {parameters.get("bloom_coeff", 0.0):.6f},
  "deposition_coeff": {parameters.get("deposition_coeff", 0.0):.6f},
  "flushing_coeff": {parameters.get("flushing_coeff", 0.0):.6f},
  "purification_coeff": {parameters.get("purification_coeff", 0.0):.6f},
  "floc_coeff": {parameters.get("floc_coeff", 0.0):.6f},
  "temp_optimum": {parameters.get("temp_optimum", 0.0):.6f},
  "temp_width": {parameters.get("temp_width", 0.0):.6f},
  "n_half_sat": {parameters.get("n_half_sat", 0.0):.6f},
  "p_half_sat": {parameters.get("p_half_sat", 0.0):.6f},
  "light_threshold": {parameters.get("light_threshold", 0.0):.6f},
  "light_sharpness": {parameters.get("light_sharpness", 0.0):.6f},
  "flow_optimum": {parameters.get("flow_optimum", 0.0):.6f},
  "flow_width": {parameters.get("flow_width", 0.0):.6f},
  "do_midpoint": {parameters.get("do_midpoint", 0.0):.6f},
  "do_sharpness": {parameters.get("do_sharpness", 0.0):.6f},
  "fusion_ratio": {coefficients.get("fusion_ratio", 0.0):.6f}
}}
```

## 4. Scope statement

- Current data scope: {data_summary.get("notes", {}).get("current_scope", "single-station prototype")}
- Boundary head: {data_summary.get("notes", {}).get("boundary_detection_head", "reserved")}
- Spatial graph statement: {data_summary.get("notes", {}).get("spatial_graph", "feature-factor graph")}
- Current physics stage: explicit process surrogate on daily single-station data, not a calibrated 2D PDE solver
"""


def export_physics_note(
    path: str | Path, coefficients: dict[str, Any], data_summary: dict[str, Any]
) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    content = build_physics_markdown(coefficients=coefficients, data_summary=data_summary)
    path.write_text(content, encoding="utf-8")
    return path
