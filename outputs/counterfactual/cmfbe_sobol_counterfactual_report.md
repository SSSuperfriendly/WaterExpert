# CMFBE Sobol And Counterfactual Prototype

## 1. Scope

- Test window: `2024-09-07` to `2024-12-31`.
- Days analyzed: `92`.
- Response analyzed: `net_process_response = source_total - sink_total` from the current learned CMFBE surrogate.
- Status: prototype Sobol-style Monte Carlo sensitivity and one-factor counterfactual intervention analysis.

## 2. Top Sobol Factors

| Factor | First-order | Total-order |
| --- | ---: | ---: |
| runoff_sediment_pulse | 0.5933 | 0.6083 |
| songpu_flushing_potential | 0.1966 | 0.2947 |
| precipitation_3d | 0.0759 | 0.0598 |
| songpu_flow_m3s_abs | 0.0173 | 0.0155 |
| dissolved_oxygen | 0.0198 | 0.0109 |
| huangdu_flow_m3s_abs | -0.0068 | 0.0048 |
| self_purification_index | 0.0073 | 0.0031 |
| water_temp | 0.0005 | 0.0000 |
| conductivity | -0.0001 | 0.0000 |
| songpu_water_level_m_1d_diff | -0.0001 | 0.0000 |

## 3. Strongest Counterfactual Responses

| Factor | Intervention | Mean net-process delta | Mean turbidity delta | Positive-day change |
| --- | --- | ---: | ---: | ---: |
| precipitation_3d | set_to_threshold | 0.1448 | 15.7123 | 0.1522 |
| songpu_flushing_potential | set_to_threshold | 0.0949 | 4.3828 | 0.0000 |
| songpu_flushing_potential | minus_20pct | 0.0373 | 4.2547 | 0.0109 |
| songpu_flushing_potential | plus_20pct | -0.0314 | -3.5077 | -0.0543 |
| songpu_flow_m3s_abs | set_to_threshold | -0.0162 | -2.3257 | -0.0435 |
| dissolved_oxygen | minus_20pct | 0.0146 | 1.5546 | 0.0000 |
| songpu_flow_m3s_abs | minus_20pct | 0.0115 | 1.1925 | 0.0000 |
| huangdu_flow_m3s_abs | set_to_threshold | 0.0113 | 1.6457 | 0.0326 |
| dissolved_oxygen | plus_20pct | -0.0104 | -1.1697 | -0.0217 |
| songpu_flow_m3s_abs | plus_20pct | -0.0094 | -0.9596 | -0.0109 |
| runoff_sediment_pulse | minus_20pct | -0.0072 | -1.4603 | -0.0109 |
| runoff_sediment_pulse | plus_20pct | 0.0060 | 1.2477 | 0.0000 |

## 4. Guardrails

- These Sobol indices are prototype Monte Carlo estimates over the current single-station CMFBE surrogate, not full calibrated hydrodynamic uncertainty indices.
- These counterfactuals are one-factor interventions on the learned surrogate, not validated engineering treatment outcomes.
- Use these outputs to prioritize mechanistic inspection and data collection, not to claim operational policy optimality.