from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def _series(frame: pd.DataFrame, column: str, default: float = 0.0) -> np.ndarray:
    if column not in frame.columns:
        return np.full(len(frame), float(default), dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default).to_numpy(dtype=float)


def evaluate_cmfbe_surrogate(
    frame: pd.DataFrame,
    coefficients: dict[str, Any],
) -> pd.DataFrame:
    params = coefficients.get("parameters", {})
    result = frame.copy()

    songpu_flow = np.clip(_series(result, "songpu_flow_m3s_abs"), a_min=0.0, a_max=None)
    huangdu_flow = np.clip(_series(result, "huangdu_flow_m3s_abs"), a_min=0.0, a_max=None)
    songpu_level = np.clip(np.abs(_series(result, "songpu_water_level_m")), a_min=0.0, a_max=None)
    wind_speed = np.clip(_series(result, "wind_speed"), a_min=0.0, a_max=None)
    stage_jump = np.clip(
        np.abs(_series(result, "songpu_water_level_m_1d_diff")), a_min=0.0, a_max=None
    )
    current_turbidity = np.clip(_series(result, "turbidity"), a_min=0.0, a_max=None)
    current_log_turbidity = np.log1p(current_turbidity)
    available_sediment = current_log_turbidity / (1.0 + current_log_turbidity)

    velocity_proxy = (
        params["velocity_flow_scale"] * np.log1p(songpu_flow)
        + params["velocity_aux_flow_scale"] * np.log1p(huangdu_flow)
    ) / (1.0 + params["velocity_depth_scale"] * np.log1p(songpu_level))
    bed_shear_proxy = (
        params["shear_flow_scale"] * np.square(velocity_proxy)
        + params["shear_wind_scale"] * np.log1p(wind_speed)
        + params["shear_stage_scale"] * np.log1p(stage_jump)
    )

    reverse_flag = np.clip(_series(result, "songpu_flow_m3s_reverse_flag"), 0.0, 1.0)
    rise_flag = np.clip(_series(result, "songpu_flow_rise_flag"), 0.0, 1.0)
    erosion_excess = np.log1p(np.exp(bed_shear_proxy - params["erosion_threshold"]))
    erosion_source = params["erosion_coeff"] * erosion_excess * (
        1.0 + 0.5 * reverse_flag + 0.25 * rise_flag
    )

    runoff_driver = np.log1p(np.clip(_series(result, "runoff_sediment_pulse"), 0.0, None))
    runoff_driver += 0.35 * np.log1p(np.clip(_series(result, "precipitation_3d"), 0.0, None))
    runoff_driver += 0.25 * np.log1p(np.clip(_series(result, "huangdu_flow_m3s_abs"), 0.0, None))
    runoff_source = params["runoff_coeff"] * runoff_driver

    tidal_driver = np.log1p(np.clip(_series(result, "songpu_tidal_pumping_proxy"), 0.0, None))
    tidal_driver += 0.30 * np.log1p(
        np.clip(np.abs(_series(result, "songpu_flow_level_coupling")), 0.0, None)
    )
    tidal_source = params["tidal_coeff"] * tidal_driver

    water_temp = np.clip(_series(result, "water_temp"), 0.0, None)
    total_n = np.clip(_series(result, "tn"), 0.0, None) + 0.5 * np.clip(
        _series(result, "nh3_n"), 0.0, None
    )
    total_p = np.clip(_series(result, "tp"), 0.0, None)
    seasonal_light = np.clip(0.5 * (1.0 + _series(result, "dayofyear_sin")), 0.0, 1.0)
    nutrient_n_factor = total_n / (total_n + params["n_half_sat"] + 1e-6)
    nutrient_p_factor = total_p / (total_p + params["p_half_sat"] + 1e-6)
    nutrient_factor = np.minimum(nutrient_n_factor, nutrient_p_factor)
    temp_factor = np.exp(-np.square((water_temp - params["temp_optimum"]) / (params["temp_width"] + 1e-6)))
    light_factor = _sigmoid(params["light_sharpness"] * (seasonal_light - params["light_threshold"]))
    flow_growth_factor = _sigmoid(
        4.0 * (params["flow_optimum"] - velocity_proxy) / (params["flow_width"] + 1e-6)
    )
    phytoplankton_source = (
        params["bloom_coeff"] * temp_factor * light_factor * nutrient_factor * flow_growth_factor
    )

    conductivity = np.clip(np.abs(_series(result, "conductivity")), 0.0, None)
    floc_factor = 1.0 + params["floc_coeff"] * np.tanh(np.log1p(conductivity) / 5.0)
    settling_index = np.clip(_series(result, "settling_index"), 0.0, None)
    deposition_efficiency = _sigmoid(
        4.0 * (params["deposition_threshold"] - bed_shear_proxy) / (params["flow_width"] + 1e-6)
    )
    krone_deposition_sink = (
        params["deposition_coeff"]
        * available_sediment
        * deposition_efficiency
        * floc_factor
        * (1.0 + 0.25 * np.log1p(settling_index))
    )

    flushing_potential = np.clip(_series(result, "songpu_flushing_potential"), 0.0, None)
    flushing_sink = (
        params["flushing_coeff"]
        * available_sediment
        * velocity_proxy
        * np.log1p(flushing_potential)
    )

    dissolved_oxygen = np.clip(_series(result, "dissolved_oxygen"), 0.0, None)
    self_purification_index = np.clip(_series(result, "self_purification_index"), 0.0, None)
    do_factor = _sigmoid(params["do_sharpness"] * (dissolved_oxygen - params["do_midpoint"]))
    purification_sink = (
        params["purification_coeff"]
        * available_sediment
        * do_factor
        * np.log1p(self_purification_index)
    )

    source_total = runoff_source + erosion_source + tidal_source + phytoplankton_source
    sink_total = krone_deposition_sink + flushing_sink + purification_sink
    physics_delta_log_turbidity = source_total - sink_total
    physics_log_turbidity_next = np.clip(
        current_log_turbidity + physics_delta_log_turbidity, a_min=0.0, a_max=None
    )
    physics_turbidity_next = np.expm1(physics_log_turbidity_next)

    result["velocity_proxy"] = velocity_proxy
    result["bed_shear_proxy"] = bed_shear_proxy
    result["erosion_source"] = erosion_source
    result["runoff_source"] = runoff_source
    result["tidal_source"] = tidal_source
    result["phytoplankton_source"] = phytoplankton_source
    result["krone_deposition_sink"] = krone_deposition_sink
    result["flushing_sink"] = flushing_sink
    result["purification_sink"] = purification_sink
    result["source_total"] = source_total
    result["sink_total"] = sink_total
    result["net_process_response"] = physics_delta_log_turbidity
    result["physics_log_turbidity_next"] = physics_log_turbidity_next
    result["physics_turbidity_next"] = physics_turbidity_next
    return result
