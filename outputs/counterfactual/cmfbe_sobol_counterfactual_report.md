# CMFBE Sobol And Counterfactual Prototype

## 1. Scope

- Test window: `2024-09-07` to `2024-12-31`.
- Days analyzed: `92`.
- Response analyzed: `net_process_response = source_total - sink_total` from the current learned CMFBE surrogate.
- Status: prototype Sobol-style Monte Carlo sensitivity, single-factor counterfactuals, and linked multi-factor interventions.

## 2. Top Sobol Factors

| Factor | First-order | Total-order | Interaction |
| --- | ---: | ---: | ---: |
| runoff_sediment_pulse | 0.6652 | 0.7082 | 0.0430 |
| songpu_flushing_potential | 0.0874 | 0.1887 | 0.1013 |
| precipitation_3d | 0.0897 | 0.0696 | 0.0000 |
| songpu_flow_m3s_abs | 0.0129 | 0.0100 | 0.0000 |
| dissolved_oxygen | 0.0204 | 0.0097 | 0.0000 |
| huangdu_flow_m3s_abs | -0.0072 | 0.0083 | 0.0155 |
| self_purification_index | 0.0076 | 0.0024 | 0.0000 |
| water_temp | 0.0021 | 0.0001 | 0.0000 |
| conductivity | -0.0001 | 0.0000 | 0.0001 |
| songpu_water_level_m_1d_diff | -0.0001 | 0.0000 | 0.0001 |

## 3. Strongest Single-Factor Counterfactuals

| Factor | Intervention | Mean net-process delta | Mean turbidity delta | Improved-day fraction |
| --- | --- | ---: | ---: | ---: |
| songpu_flushing_potential | plus_20pct | -0.0278 | -3.8789 | 1.0000 |
| songpu_flow_m3s_abs | set_to_threshold | -0.0143 | -2.4610 | 0.8696 |
| runoff_sediment_pulse | minus_20pct | -0.0086 | -2.4391 | 0.2500 |
| dissolved_oxygen | plus_20pct | -0.0108 | -1.4384 | 1.0000 |
| precipitation_3d | minus_20pct | -0.0062 | -1.3280 | 0.5543 |
| songpu_flow_m3s_abs | plus_20pct | -0.0083 | -1.0519 | 1.0000 |
| huangdu_flow_m3s_abs | minus_20pct | -0.0062 | -1.0421 | 1.0000 |
| huangdu_flow_m3s_abs | plus_20pct | 0.0052 | 0.8727 | 0.0000 |
| precipitation_3d | plus_20pct | 0.0052 | 1.1239 | 0.0000 |
| songpu_flow_m3s_abs | minus_20pct | 0.0102 | 1.3042 | 0.0000 |
| dissolved_oxygen | minus_20pct | 0.0152 | 1.9088 | 0.0000 |
| runoff_sediment_pulse | plus_20pct | 0.0072 | 2.0921 | 0.0000 |

## 4. Linked Multi-Factor Interventions

| Bundle | Factors | Mean turbidity delta | Improved-day fraction | Synergy vs additive |
| --- | --- | ---: | ---: | ---: |
| top_3_linked_intervention | 3-day cumulative precipitation|Songpu flushing potential|Songpu absolute flow | -7.8276 | 1.0000 | -0.1597 |
| top_2_linked_intervention | 3-day cumulative precipitation|Songpu flushing potential | -5.1747 | 1.0000 | 0.0322 |

## 5. Guardrails

- These Sobol indices are prototype Monte Carlo estimates over the current single-station CMFBE surrogate, not full calibrated hydrodynamic uncertainty indices.
- These counterfactuals are surrogate interventions on learned mechanism factors, not validated engineering treatment outcomes.
- Use these outputs to prioritize mechanistic inspection, linked-factor monitoring, and agent retrieval, not to claim operational policy optimality.