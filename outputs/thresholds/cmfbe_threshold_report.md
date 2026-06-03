# CMFBE-ST-GCN Threshold Response Analysis

## 1. Analysis Scope

- Source: `CMFBE-ST-GCN` test-window outputs from the current Wusongkou daily prototype.
- Window: `2024-09-07` to `2024-12-31`, `92` days.
- Response variable: `net_process_response = source_total - sink_total`, representing net turbidity forcing after subtracting self-purification and export sinks.
- Threshold meaning: an empirical critical level at which the prototype becomes more likely to shift toward self-purification failure or rapid turbidity increase.
- Method: one-breakpoint piecewise linear fit, selected by maximum explanatory gain over a global linear fit.
- Boundary: these are empirical thresholds from the current model-and-data configuration, not calibrated 2D hydrodynamic physical thresholds.

## 2. Global Threshold Candidates

| Factor | Threshold | Unit | Piecewise R2 | R2 Gain | Response Jump | Confidence |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| 3-day cumulative precipitation | 49.1000 | mm | 0.406 | 0.251 | 0.409 | high |
| Songpu flushing potential | 3.6456 | proxy | 0.220 | 0.216 | -0.353 | high |
| Huangdu absolute flow | 22.9000 | m3/s | 0.220 | 0.175 | 0.000 | high |
| 7-day cumulative precipitation | 141.6000 | mm | 0.349 | 0.159 | 0.202 | high |
| Songpu absolute flow | 878.0000 | m3/s | 0.112 | 0.109 | 0.311 | high |
| Songpu resuspension potential | 572.4000 | proxy | 0.107 | 0.106 | -0.291 | high |
| Wind speed | 1.3167 | m/s | 0.091 | 0.082 | 0.082 | medium |
| Hydrodynamic velocity proxy | 1.1012 | dimensionless | 0.090 | 0.078 | -0.233 | medium |

## 3. Contextual Threshold Candidates

| Context Type | Context | Factor | Threshold | Unit | Piecewise R2 | R2 Gain | Response Jump | Confidence |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| temperature background | mild background | Hydrodynamic velocity proxy | 1.0621 | dimensionless | 0.477 | 0.473 | 0.249 | medium |
| temperature background | mild background | Bed shear proxy | 0.3639 | dimensionless | 0.438 | 0.390 | 0.477 | medium |
| hydrodynamic condition | moderate hydrodynamics | Bed shear proxy | 0.3544 | dimensionless | 0.662 | 0.361 | 0.816 | medium |
| hydrodynamic condition | moderate hydrodynamics | Wind speed | 1.2958 | m/s | 0.361 | 0.357 | -0.039 | medium |
| hydrodynamic condition | low hydrodynamics | Bed shear proxy | 0.3129 | dimensionless | 0.376 | 0.315 | 0.608 | medium |
| temperature background | mild background | Wind speed | 1.8417 | m/s | 0.352 | 0.295 | -0.212 | medium |
| rainfall background | normal rainfall background | 7-day cumulative precipitation | 6.5000 | mm | 0.356 | 0.279 | 0.267 | medium |
| hydrodynamic condition | moderate hydrodynamics | Hydrodynamic velocity proxy | 1.0823 | dimensionless | 0.425 | 0.271 | 0.447 | medium |
| rainfall background | heavy-rainfall background | Wind speed | 3.0750 | m/s | 0.334 | 0.270 | 0.123 | medium |
| hydrodynamic condition | moderate hydrodynamics | 7-day cumulative precipitation | 71.3000 | mm | 0.400 | 0.261 | 0.278 | medium |
| rainfall background | normal rainfall background | Wind speed | 2.0250 | m/s | 0.268 | 0.261 | -0.009 | medium |
| temperature background | warm background | 7-day cumulative precipitation | 110.8000 | mm | 0.376 | 0.257 | 0.422 | medium |
| hydrodynamic condition | low hydrodynamics | 7-day cumulative precipitation | 110.8000 | mm | 0.452 | 0.255 | 0.570 | medium |
| hydrodynamic condition | low hydrodynamics | Air temperature | 20.7417 | degC | 0.416 | 0.240 | 0.421 | medium |
| hydrodynamic condition | low hydrodynamics | Hydrodynamic velocity proxy | 0.9475 | dimensionless | 0.242 | 0.234 | 0.166 | medium |
| hydrodynamic condition | low hydrodynamics | Wind speed | 3.1625 | m/s | 0.261 | 0.234 | 0.336 | medium |
| temperature background | warm background | Wind speed | 3.5167 | m/s | 0.234 | 0.234 | 0.259 | medium |
| rainfall background | dry background | Air temperature | 17.6348 | degC | 0.513 | 0.227 | 0.011 | medium |

## 4. Interpretable Takeaways

The strongest empirical threshold signals remain concentrated in cumulative rainfall, hydrodynamic forcing, bed shear, and flushing-related transport indicators.

In operational interpretation, exceedance of these thresholds should be read as a heightened likelihood that turbidity-driving processes will dominate over self-purification and export sinks in the current prototype.

## 5. Next Data Requirements

- Upgrade empirical thresholds to physically calibrated control thresholds by adding section velocity, depth, sediment grain size, critical shear stress, and observed suspended-sediment concentration.
- Build spatial threshold maps by adding multi-station hydrodynamics or 2D hydrodynamic fields together with remote-sensing or UAV-derived clarity products.
- Build counterfactual threshold analyses by adding engineering control, restoration intervention, and external loading event records.