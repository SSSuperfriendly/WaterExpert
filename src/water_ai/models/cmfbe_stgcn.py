from __future__ import annotations

import math
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from water_ai.models.mscim import MSCIMPrototype


def _inverse_softplus(value: float) -> float:
    value = max(value, 1e-6)
    return math.log(math.expm1(value))


class CMFBE_STGCNPrototype(nn.Module):
    def __init__(
        self,
        num_features: int,
        adjacency: np.ndarray,
        feature_index: dict[str, int],
        clearness_log_min: float,
        clearness_log_max: float,
        hidden_dim: int,
        transformer_layers: int,
        num_heads: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.feature_index = feature_index
        self.backbone = MSCIMPrototype(
            num_features=num_features,
            adjacency=adjacency,
            feature_index=feature_index,
            clearness_log_min=clearness_log_min,
            clearness_log_max=clearness_log_max,
            hidden_dim=hidden_dim,
            transformer_layers=transformer_layers,
            num_heads=num_heads,
            dropout=dropout,
            enable_boundary_head=True,
        )

        # Hydrodynamic surrogate: convert flow and stage to a daily velocity-like signal.
        self.velocity_flow_scale = nn.Parameter(torch.tensor(_inverse_softplus(0.18)))
        self.velocity_aux_flow_scale = nn.Parameter(torch.tensor(_inverse_softplus(0.06)))
        self.velocity_depth_scale = nn.Parameter(torch.tensor(_inverse_softplus(0.35)))

        # Shear-stress surrogate and critical thresholds.
        self.shear_flow_scale = nn.Parameter(torch.tensor(_inverse_softplus(0.25)))
        self.shear_wind_scale = nn.Parameter(torch.tensor(_inverse_softplus(0.08)))
        self.shear_stage_scale = nn.Parameter(torch.tensor(_inverse_softplus(0.07)))
        self.erosion_threshold = nn.Parameter(torch.tensor(_inverse_softplus(0.75)))
        self.deposition_threshold = nn.Parameter(torch.tensor(_inverse_softplus(1.20)))

        # Source and sink process coefficients in daily log-turbidity space.
        self.erosion_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.18)))
        self.runoff_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.20)))
        self.tidal_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.14)))
        self.bloom_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.10)))
        self.deposition_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.18)))
        self.flushing_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.22)))
        self.purification_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.11)))
        self.floc_coeff = nn.Parameter(torch.tensor(_inverse_softplus(0.22)))

        # Eco-dynamics parameters following nutrient-light-temperature logic.
        self.temp_optimum = nn.Parameter(torch.tensor(_inverse_softplus(22.0)))
        self.temp_width = nn.Parameter(torch.tensor(_inverse_softplus(7.0)))
        self.n_half_sat = nn.Parameter(torch.tensor(_inverse_softplus(1.0)))
        self.p_half_sat = nn.Parameter(torch.tensor(_inverse_softplus(0.05)))
        self.light_threshold = nn.Parameter(torch.tensor(_inverse_softplus(0.45)))
        self.light_sharpness = nn.Parameter(torch.tensor(_inverse_softplus(4.0)))
        self.flow_optimum = nn.Parameter(torch.tensor(_inverse_softplus(0.95)))
        self.flow_width = nn.Parameter(torch.tensor(_inverse_softplus(0.45)))
        self.do_midpoint = nn.Parameter(torch.tensor(_inverse_softplus(6.0)))
        self.do_sharpness = nn.Parameter(torch.tensor(_inverse_softplus(0.80)))

        self.fusion_logit = nn.Parameter(torch.tensor(0.65))

    def _positive(self, parameter: torch.Tensor) -> torch.Tensor:
        return F.softplus(parameter)

    def _read_feature(self, raw_last: torch.Tensor, name: str) -> torch.Tensor:
        index = self.feature_index.get(name)
        if index is None:
            return torch.zeros(raw_last.size(0), device=raw_last.device, dtype=raw_last.dtype)
        return raw_last[:, index]

    def _build_velocity_proxy(self, raw_last: torch.Tensor) -> torch.Tensor:
        songpu_flow = torch.clamp(self._read_feature(raw_last, "songpu_flow_m3s_abs"), min=0.0)
        huangdu_flow = torch.clamp(self._read_feature(raw_last, "huangdu_flow_m3s_abs"), min=0.0)
        songpu_level = torch.clamp(
            torch.abs(self._read_feature(raw_last, "songpu_water_level_m")), min=0.0
        )

        flow_signal = self._positive(self.velocity_flow_scale) * torch.log1p(songpu_flow)
        flow_signal = flow_signal + self._positive(self.velocity_aux_flow_scale) * torch.log1p(
            huangdu_flow
        )
        depth_signal = 1.0 + self._positive(self.velocity_depth_scale) * torch.log1p(songpu_level)
        return flow_signal / depth_signal

    def _build_bed_shear_proxy(
        self, raw_last: torch.Tensor, velocity_proxy: torch.Tensor
    ) -> torch.Tensor:
        wind_speed = torch.clamp(self._read_feature(raw_last, "wind_speed"), min=0.0)
        stage_jump = torch.clamp(
            torch.abs(self._read_feature(raw_last, "songpu_water_level_m_1d_diff")), min=0.0
        )
        shear = self._positive(self.shear_flow_scale) * velocity_proxy.square()
        shear = shear + self._positive(self.shear_wind_scale) * torch.log1p(wind_speed)
        shear = shear + self._positive(self.shear_stage_scale) * torch.log1p(stage_jump)
        return shear

    def get_physics_coefficients(self) -> dict[str, Any]:
        return {
            "equation_family": "explicit_process_surrogate_log_turbidity_balance",
            "parameters": {
                "velocity_flow_scale": float(self._positive(self.velocity_flow_scale).item()),
                "velocity_aux_flow_scale": float(
                    self._positive(self.velocity_aux_flow_scale).item()
                ),
                "velocity_depth_scale": float(self._positive(self.velocity_depth_scale).item()),
                "shear_flow_scale": float(self._positive(self.shear_flow_scale).item()),
                "shear_wind_scale": float(self._positive(self.shear_wind_scale).item()),
                "shear_stage_scale": float(self._positive(self.shear_stage_scale).item()),
                "erosion_threshold": float(self._positive(self.erosion_threshold).item()),
                "deposition_threshold": float(self._positive(self.deposition_threshold).item()),
                "erosion_coeff": float(self._positive(self.erosion_coeff).item()),
                "runoff_coeff": float(self._positive(self.runoff_coeff).item()),
                "tidal_coeff": float(self._positive(self.tidal_coeff).item()),
                "bloom_coeff": float(self._positive(self.bloom_coeff).item()),
                "deposition_coeff": float(self._positive(self.deposition_coeff).item()),
                "flushing_coeff": float(self._positive(self.flushing_coeff).item()),
                "purification_coeff": float(self._positive(self.purification_coeff).item()),
                "floc_coeff": float(self._positive(self.floc_coeff).item()),
                "temp_optimum": float(self._positive(self.temp_optimum).item()),
                "temp_width": float(self._positive(self.temp_width).item()),
                "n_half_sat": float(self._positive(self.n_half_sat).item()),
                "p_half_sat": float(self._positive(self.p_half_sat).item()),
                "light_threshold": float(self._positive(self.light_threshold).item()),
                "light_sharpness": float(self._positive(self.light_sharpness).item()),
                "flow_optimum": float(self._positive(self.flow_optimum).item()),
                "flow_width": float(self._positive(self.flow_width).item()),
                "do_midpoint": float(self._positive(self.do_midpoint).item()),
                "do_sharpness": float(self._positive(self.do_sharpness).item()),
            },
            "process_formulas": {
                "velocity_proxy": (
                    "u* = [a_q log(1 + Q_songpu) + a_h log(1 + Q_huangdu)] / "
                    "[1 + a_d log(1 + H_songpu)]"
                ),
                "bed_shear_proxy": (
                    "tau* = a_tau u*^2 + a_w log(1 + wind_speed) + "
                    "a_hs log(1 + |dH_songpu/dt|)"
                ),
                "runoff_source": (
                    "R_runoff = k_r [log(1 + runoff_sediment_pulse) + "
                    "0.35 log(1 + precipitation_3d) + 0.25 log(1 + Q_huangdu)]"
                ),
                "erosion_source": (
                    "R_erosion = k_e softplus(tau* - tau_ce) (1 + 0.5 reverse + 0.25 rise)"
                ),
                "tidal_source": (
                    "R_tide = k_t [log(1 + tidal_pumping) + 0.3 log(1 + |flow_level_coupling|)]"
                ),
                "bloom_source": (
                    "R_bloom = k_b f_T(T) f_I(light) min(f_N(N), f_P(P)) f_v(u*)"
                ),
                "krone_deposition_sink": (
                    "S_dep = k_d A_sed sigmoid(4 (tau_cd - tau*) / w_v) (1 + beta_floc) "
                    "(1 + 0.25 log(1 + settling_index))"
                ),
                "flushing_sink": (
                    "S_flush = k_f A_sed u* log(1 + flushing_potential)"
                ),
                "purification_sink": (
                    "S_pur = k_p A_sed f_DO(DO) log(1 + self_purification_index)"
                ),
                "physics_balance": (
                    "log(1 + T_{t+1}) = clamp(log(1 + T_t) + "
                    "R_runoff + R_erosion + R_tide + R_bloom - "
                    "S_dep - S_flush - S_pur, 0)"
                ),
            },
            "fusion_ratio": float(torch.sigmoid(self.fusion_logit).item()),
            "clearness_proxy_note": (
                "Final clearness proxy is derived from fused turbidity prediction using the "
                "same monotonic transform as the dataset target."
            ),
        }

    def forward(self, x: torch.Tensor, x_raw: torch.Tensor) -> dict[str, torch.Tensor]:
        backbone_output = self.backbone(x, x_raw=x_raw)
        raw_last = x_raw[:, -1, :]

        current_turbidity = torch.clamp(self._read_feature(raw_last, "turbidity"), min=0.0)
        current_log_turbidity = torch.log1p(current_turbidity)
        available_sediment = current_log_turbidity / (1.0 + current_log_turbidity)

        velocity_proxy = self._build_velocity_proxy(raw_last)
        bed_shear_proxy = self._build_bed_shear_proxy(raw_last, velocity_proxy)

        reverse_flag = torch.clamp(
            self._read_feature(raw_last, "songpu_flow_m3s_reverse_flag"), min=0.0, max=1.0
        )
        rise_flag = torch.clamp(
            self._read_feature(raw_last, "songpu_flow_rise_flag"), min=0.0, max=1.0
        )
        erosion_excess = F.softplus(bed_shear_proxy - self._positive(self.erosion_threshold))
        erosion_source = self._positive(self.erosion_coeff) * erosion_excess * (
            1.0 + 0.5 * reverse_flag + 0.25 * rise_flag
        )

        runoff_driver = torch.log1p(
            torch.clamp(self._read_feature(raw_last, "runoff_sediment_pulse"), min=0.0)
        )
        runoff_driver = runoff_driver + 0.35 * torch.log1p(
            torch.clamp(self._read_feature(raw_last, "precipitation_3d"), min=0.0)
        )
        runoff_driver = runoff_driver + 0.25 * torch.log1p(
            torch.clamp(self._read_feature(raw_last, "huangdu_flow_m3s_abs"), min=0.0)
        )
        runoff_source = self._positive(self.runoff_coeff) * runoff_driver

        tidal_driver = torch.log1p(
            torch.clamp(self._read_feature(raw_last, "songpu_tidal_pumping_proxy"), min=0.0)
        )
        tidal_driver = tidal_driver + 0.30 * torch.log1p(
            torch.clamp(
                torch.abs(self._read_feature(raw_last, "songpu_flow_level_coupling")), min=0.0
            )
        )
        tidal_source = self._positive(self.tidal_coeff) * tidal_driver

        water_temp = torch.clamp(self._read_feature(raw_last, "water_temp"), min=0.0)
        total_n = torch.clamp(self._read_feature(raw_last, "tn"), min=0.0) + 0.5 * torch.clamp(
            self._read_feature(raw_last, "nh3_n"), min=0.0
        )
        total_p = torch.clamp(self._read_feature(raw_last, "tp"), min=0.0)
        seasonal_light = torch.clamp(
            0.5 * (1.0 + self._read_feature(raw_last, "dayofyear_sin")), min=0.0, max=1.0
        )
        nutrient_n_factor = total_n / (total_n + self._positive(self.n_half_sat) + 1e-6)
        nutrient_p_factor = total_p / (total_p + self._positive(self.p_half_sat) + 1e-6)
        nutrient_factor = torch.minimum(nutrient_n_factor, nutrient_p_factor)
        temp_factor = torch.exp(
            -(
                (water_temp - self._positive(self.temp_optimum))
                / (self._positive(self.temp_width) + 1e-6)
            ).square()
        )
        light_factor = torch.sigmoid(
            self._positive(self.light_sharpness)
            * (seasonal_light - self._positive(self.light_threshold))
        )
        flow_growth_factor = torch.sigmoid(
            4.0
            * (
                self._positive(self.flow_optimum) - velocity_proxy
            )
            / (self._positive(self.flow_width) + 1e-6)
        )
        phytoplankton_source = self._positive(self.bloom_coeff) * temp_factor * light_factor * (
            nutrient_factor * flow_growth_factor
        )

        conductivity = torch.clamp(
            torch.abs(self._read_feature(raw_last, "conductivity")), min=0.0
        )
        floc_factor = 1.0 + self._positive(self.floc_coeff) * torch.tanh(
            torch.log1p(conductivity) / 5.0
        )
        settling_index = torch.clamp(self._read_feature(raw_last, "settling_index"), min=0.0)
        deposition_efficiency = torch.sigmoid(
            4.0
            * (
                self._positive(self.deposition_threshold) - bed_shear_proxy
            )
            / (self._positive(self.flow_width) + 1e-6)
        )
        krone_deposition_sink = (
            self._positive(self.deposition_coeff)
            * available_sediment
            * deposition_efficiency
            * floc_factor
            * (1.0 + 0.25 * torch.log1p(settling_index))
        )

        flushing_potential = torch.clamp(
            self._read_feature(raw_last, "songpu_flushing_potential"), min=0.0
        )
        flushing_sink = (
            self._positive(self.flushing_coeff)
            * available_sediment
            * velocity_proxy
            * torch.log1p(flushing_potential)
        )

        dissolved_oxygen = torch.clamp(
            self._read_feature(raw_last, "dissolved_oxygen"), min=0.0
        )
        self_purification_index = torch.clamp(
            self._read_feature(raw_last, "self_purification_index"), min=0.0
        )
        do_factor = torch.sigmoid(
            self._positive(self.do_sharpness)
            * (dissolved_oxygen - self._positive(self.do_midpoint))
        )
        purification_sink = (
            self._positive(self.purification_coeff)
            * available_sediment
            * do_factor
            * torch.log1p(self_purification_index)
        )

        source_total = runoff_source + erosion_source + tidal_source + phytoplankton_source
        sink_total = krone_deposition_sink + flushing_sink + purification_sink
        physics_delta_log_turbidity = source_total - sink_total
        physics_log_turbidity_pred = torch.clamp(
            current_log_turbidity + physics_delta_log_turbidity, min=0.0
        )
        physics_turbidity_pred = torch.expm1(physics_log_turbidity_pred)
        physics_clearness_pred = self.backbone.derive_clearness_from_log_turbidity(
            physics_log_turbidity_pred
        )

        fusion_ratio = torch.sigmoid(self.fusion_logit)
        log_turbidity_pred = fusion_ratio * backbone_output["log_turbidity_pred"] + (
            1.0 - fusion_ratio
        ) * physics_log_turbidity_pred
        turbidity_pred = torch.expm1(log_turbidity_pred)
        clearness_pred = self.backbone.derive_clearness_from_log_turbidity(log_turbidity_pred)

        return {
            **backbone_output,
            "velocity_proxy": velocity_proxy,
            "bed_shear_proxy": bed_shear_proxy,
            "erosion_source": erosion_source,
            "runoff_source": runoff_source,
            "tidal_source": tidal_source,
            "phytoplankton_source": phytoplankton_source,
            "krone_deposition_sink": krone_deposition_sink,
            "flushing_sink": flushing_sink,
            "purification_sink": purification_sink,
            "source_total": source_total,
            "sink_total": sink_total,
            "physics_delta_log_turbidity": physics_delta_log_turbidity,
            "physics_log_turbidity_pred": physics_log_turbidity_pred,
            "physics_turbidity_pred": physics_turbidity_pred,
            "physics_clearness_pred": physics_clearness_pred,
            "fusion_ratio": fusion_ratio.expand_as(turbidity_pred),
            "turbidity_pred": turbidity_pred,
            "log_turbidity_pred": log_turbidity_pred,
            "clearness_pred": clearness_pred,
        }
