from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from ..models.cmfbe_stgcn import CMFBE_STGCNPrototype
from ..models.mscim import MSCIMPrototype


@dataclass
class CheckpointPrediction:
    outputs: dict[str, Any]
    feature_values: dict[str, float]
    top_features: list[dict[str, float]]


class TimeSeriesCheckpointRunner:
    """Lazy checkpoint loader for single-state agent inference."""

    def __init__(
        self,
        checkpoint_path: str,
        model_kind: str,
        data_path: str = "outputs/intermediate/multimodal_daily_dataset.csv",
        device: str = "auto",
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.model_kind = model_kind
        self.data_path = Path(data_path)
        self.device_name = device
        self.device = self._choose_device(device)
        self.loaded = False
        self.load_error: str | None = None

        self.model: torch.nn.Module | None = None
        self.meta: dict[str, Any] = {}
        self.feature_columns: list[str] = []
        self.feature_index: dict[str, int] = {}
        self.history_days = 21
        self.feature_defaults: dict[str, float] = {}
        self.feature_means: dict[str, float] = {}
        self.feature_scales: dict[str, float] = {}

    def _choose_device(self, device: str) -> torch.device:
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(device)

    def predict(self, state: dict[str, Any]) -> CheckpointPrediction:
        self._ensure_loaded()
        if self.model is None:
            raise RuntimeError(self.load_error or "checkpoint model is not loaded")

        raw_vector = self._state_to_raw_vector(state)
        raw_window = self._build_raw_window(raw_vector, state)
        scaled_window = self._scale_window(raw_window)
        x = torch.tensor(scaled_window[None, :, :], dtype=torch.float32, device=self.device)
        x_raw = torch.tensor(raw_window[None, :, :], dtype=torch.float32, device=self.device)

        self.model.eval()
        with torch.no_grad():
            outputs = self.model(x, x_raw=x_raw)

        parsed_outputs = self._parse_outputs(outputs)
        return CheckpointPrediction(
            outputs=parsed_outputs,
            feature_values={
                feature: float(raw_vector[index]) for feature, index in self.feature_index.items()
            },
            top_features=self._top_features(outputs),
        )

    @property
    def ready(self) -> bool:
        """Whether the checkpoint actually loaded — loading it first if need be.

        Readiness must not be a question about whether anyone has asked yet.
        ``model`` is ``None`` until the first prediction, so a health check that
        only reads it reports a cold, perfectly good agent as broken, and then
        reports it healthy the moment the first request warms it. Neither
        reading is a fact about the checkpoint. This forces the load — once per
        process, cached by ``loaded`` — and answers about the result.
        """
        self._ensure_loaded()
        return self.model is not None

    def _ensure_loaded(self) -> None:
        if self.loaded:
            return
        self.loaded = True

        if not self.checkpoint_path.exists():
            self.load_error = f"checkpoint not found: {self.checkpoint_path}"
            return

        try:
            checkpoint = torch.load(self.checkpoint_path, map_location=self.device)
            state_dict = checkpoint["state_dict"]
            self.meta = checkpoint.get("meta", {})
            self.feature_columns = list(self.meta.get("feature_columns", []))
            if not self.feature_columns:
                raise ValueError("checkpoint meta missing feature_columns")
            self.feature_index = {
                str(key): int(value)
                for key, value in self.meta.get("feature_index", {}).items()
            } or {feature: idx for idx, feature in enumerate(self.feature_columns)}
            self.history_days = int(self.meta.get("history_days", 21))

            adjacency = self._adjacency_from_state_dict(state_dict)
            model_kwargs = self._model_kwargs(state_dict, adjacency)
            if self.model_kind == "cmfbe":
                model = CMFBE_STGCNPrototype(**model_kwargs)
            elif self.model_kind == "mscim":
                model = MSCIMPrototype(
                    **model_kwargs,
                    enable_boundary_head=any(key.startswith("boundary_head.") for key in state_dict),
                )
            else:
                raise ValueError(f"unsupported model kind: {self.model_kind}")

            model.load_state_dict(state_dict, strict=True)
            model.to(self.device)
            model.eval()
            self.model = model
            self._load_feature_statistics()
        except Exception as exc:
            self.load_error = str(exc)
            self.model = None

    def _adjacency_from_state_dict(self, state_dict: dict[str, torch.Tensor]) -> np.ndarray:
        for key in ("graph_block.adjacency", "backbone.graph_block.adjacency"):
            if key in state_dict:
                return state_dict[key].detach().cpu().numpy().astype(np.float32)
        return np.eye(len(self.feature_columns), dtype=np.float32)

    def _model_kwargs(self, state_dict: dict[str, torch.Tensor], adjacency: np.ndarray) -> dict[str, Any]:
        projection_key = (
            "backbone.input_projection.weight"
            if self.model_kind == "cmfbe"
            else "input_projection.weight"
        )
        hidden_dim = int(state_dict[projection_key].shape[0])
        layer_token = (
            "backbone.temporal_encoder.layers."
            if self.model_kind == "cmfbe"
            else "temporal_encoder.layers."
        )
        transformer_layers = len(
            {
                key.split(layer_token, 1)[1].split(".", 1)[0]
                for key in state_dict
                if layer_token in key
            }
        )
        num_heads = 4 if hidden_dim % 4 == 0 else 1
        clearness = self.meta.get("clearness_transform", {}) or {}
        return {
            "num_features": len(self.feature_columns),
            "adjacency": adjacency,
            "feature_index": self.feature_index,
            "clearness_log_min": float(clearness.get("log_turbidity_min", 0.0)),
            "clearness_log_max": float(clearness.get("log_turbidity_max", 6.0)),
            "hidden_dim": hidden_dim,
            "transformer_layers": transformer_layers,
            "num_heads": num_heads,
            "max_sequence_length": self._sequence_length(state_dict),
            "dropout": 0.0,
        }

    def _sequence_length(self, state_dict: dict[str, torch.Tensor]) -> int:
        """The look-back window the checkpoint was trained with.

        Read off the position embedding rather than from ``meta['history_days']``,
        for the same reason ``hidden_dim`` is read off the projection: the
        tensor is what has to match, and when the two disagree the tensor is the
        one `load_state_dict` will complain about.

        The window is architecture, not a setting, and leaving it to the model's
        own default is how every checkpoint came to be rejected — the models
        default to 32 days, the checkpoints carry 21, and a rejected checkpoint
        is a silent downgrade to rule-based inference rather than an error
        anyone sees.
        """
        for key in ("backbone.position_embedding", "position_embedding"):
            embedding = state_dict.get(key)
            if embedding is not None and embedding.dim() == 3:
                return int(embedding.shape[1])
        # A checkpoint with no position embedding at all: the model's own
        # default is right, and history_days is the best available statement of
        # what the training window was.
        return int(self.history_days)

    def _load_feature_statistics(self) -> None:
        if self.data_path.exists():
            frame = pd.read_csv(self.data_path)
            frame = frame.sort_values("date").reset_index(drop=True) if "date" in frame.columns else frame
            train_ratio = float(self.meta.get("train_ratio", 0.7))
            train_end = max(1, int(len(frame) * train_ratio))
            train_frame = frame.iloc[:train_end].copy()
            feature_frame = train_frame.reindex(columns=self.feature_columns)
            feature_frame = feature_frame.apply(pd.to_numeric, errors="coerce")
            medians = feature_frame.median(numeric_only=True).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            means = feature_frame.mean(numeric_only=True).replace([np.inf, -np.inf], np.nan).fillna(medians)
            scales = feature_frame.std(numeric_only=True, ddof=0).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        else:
            medians = pd.Series(0.0, index=self.feature_columns)
            means = pd.Series(0.0, index=self.feature_columns)
            scales = pd.Series(1.0, index=self.feature_columns)

        self.feature_defaults = {
            feature: self._finite(medians.get(feature, 0.0), 0.0)
            for feature in self.feature_columns
        }
        self.feature_means = {
            feature: self._finite(means.get(feature, self.feature_defaults[feature]), self.feature_defaults[feature])
            for feature in self.feature_columns
        }
        self.feature_scales = {
            feature: max(self._finite(scales.get(feature, 1.0), 1.0), 1e-6)
            for feature in self.feature_columns
        }

    def _state_to_raw_vector(self, state: dict[str, Any]) -> np.ndarray:
        values = np.array(
            [self.feature_defaults.get(feature, 0.0) for feature in self.feature_columns],
            dtype=np.float32,
        )
        derived = self._derive_features(state)
        for feature, index in self.feature_index.items():
            value = self._state_value(state, feature)
            if value is None:
                value = derived.get(feature)
            if value is not None:
                values[index] = self._finite(value, float(values[index]))
        return values

    def _build_raw_window(self, raw_vector: np.ndarray, state: dict[str, Any]) -> np.ndarray:
        window = np.repeat(raw_vector[None, :], self.history_days, axis=0).astype(np.float32)
        date_text = state.get("date")
        if date_text and "dayofyear_sin" in self.feature_index and "dayofyear_cos" in self.feature_index:
            try:
                current_date = pd.to_datetime(date_text)
                for offset in range(self.history_days):
                    date = current_date - pd.Timedelta(days=self.history_days - offset - 1)
                    day_angle = 2.0 * math.pi * float(date.dayofyear) / 366.0
                    window[offset, self.feature_index["dayofyear_sin"]] = math.sin(day_angle)
                    window[offset, self.feature_index["dayofyear_cos"]] = math.cos(day_angle)
            except Exception:
                pass
        return window

    def _scale_window(self, raw_window: np.ndarray) -> np.ndarray:
        means = np.array([self.feature_means.get(feature, 0.0) for feature in self.feature_columns], dtype=np.float32)
        scales = np.array([self.feature_scales.get(feature, 1.0) for feature in self.feature_columns], dtype=np.float32)
        return (raw_window - means[None, :]) / scales[None, :]

    def _parse_outputs(self, outputs: dict[str, torch.Tensor]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for key, value in outputs.items():
            if not torch.is_tensor(value):
                continue
            tensor = value.detach().cpu()
            if tensor.numel() == 1:
                parsed[key] = float(tensor.reshape(-1)[0])
            elif tensor.dim() == 1 and tensor.shape[0] == 1:
                parsed[key] = float(tensor[0])
        return parsed

    def _top_features(self, outputs: dict[str, torch.Tensor], top_k: int = 5) -> list[dict[str, float]]:
        saliency = outputs.get("causal_saliency")
        if not torch.is_tensor(saliency):
            return []
        scores = saliency.detach().cpu().numpy().reshape(-1)
        order = np.argsort(scores)[::-1][:top_k]
        return [
            {"feature": self.feature_columns[int(index)], "importance": float(scores[int(index)])}
            for index in order
        ]

    def _state_value(self, state: dict[str, Any], feature: str) -> float | None:
        aliases = {
            "water_temp": ("water_temp", "temperature"),
            "precipitation": ("precipitation", "rainfall"),
            "precipitation_3d": ("precipitation_3d", "rainfall_3d"),
            "precipitation_7d": ("precipitation_7d", "rainfall_7d"),
            "codmn": ("codmn", "cod_mn"),
            "nh3_n": ("nh3_n", "ammonia_n"),
            "tp": ("tp", "total_phosphorus"),
            "tn": ("tn", "total_nitrogen"),
        }
        for key in aliases.get(feature, (feature,)):
            if key in state:
                return self._finite(state.get(key), self.feature_defaults.get(feature, 0.0))
        return None

    def _derive_features(self, state: dict[str, Any]) -> dict[str, float]:
        precipitation = self._finite(state.get("precipitation", state.get("rainfall", 0.0)), 0.0)
        rainfall_3d = self._finite(state.get("rainfall_3d", state.get("precipitation_3d", precipitation)), precipitation)
        rainfall_7d = self._finite(state.get("rainfall_7d", state.get("precipitation_7d", rainfall_3d)), rainfall_3d)
        water_temp = self._finite(state.get("water_temp", state.get("temperature", 15.0)), 15.0)
        air_temp = self._finite(state.get("air_temp", water_temp), water_temp)
        conductivity = self._finite(state.get("conductivity", self.feature_defaults.get("conductivity", 0.0)), 0.0)
        songpu_flow = self._finite(state.get("songpu_flow_m3s", state.get("flow_rate", 0.0)), 0.0)
        huangdu_flow = self._finite(state.get("huangdu_flow_m3s", 0.0), 0.0)
        songpu_level = self._finite(state.get("songpu_water_level_m", 0.0), 0.0)
        huangdu_level = self._finite(state.get("huangdu_water_level_m", 0.0), 0.0)
        wind_dir = self._finite(state.get("wind_dir", 0.0), 0.0)
        wind_angle = math.radians(wind_dir)
        date = pd.to_datetime(state.get("date"), errors="coerce") if state.get("date") else None
        dayofyear = int(date.dayofyear) if date is not None and not pd.isna(date) else 1
        day_angle = 2.0 * math.pi * float(dayofyear) / 366.0
        flow_level_coupling = songpu_flow * songpu_level
        hydro_intensity = abs(songpu_flow) + abs(huangdu_flow)
        return {
            "precipitation_3d": rainfall_3d,
            "precipitation_7d": rainfall_7d,
            "pressure_drop": self._finite(state.get("pressure_drop", 0.0), 0.0),
            "resuspension_index": abs(songpu_flow) * 0.01 + self._finite(state.get("wind_speed", 0.0), 0.0) * 0.05,
            "runoff_proxy": rainfall_3d * 0.1,
            "nutrient_risk_index": self._finite(state.get("tp", 0.0), 0.0) + 0.1 * self._finite(state.get("tn", 0.0), 0.0),
            "self_purification_index": max(self._finite(state.get("dissolved_oxygen", 0.0), 0.0) - 6.0, 0.0),
            "mixing_proxy": self._finite(state.get("wind_speed", 0.0), 0.0) + 0.01 * hydro_intensity,
            "settling_index": max(0.0, 1.0 - min(abs(songpu_flow) / 100.0, 1.0)),
            "hydrodynamic_intensity": hydro_intensity,
            "conductivity_anomaly": conductivity - self.feature_defaults.get("conductivity", conductivity),
            "water_air_temp_gap": water_temp - air_temp,
            "wind_dir_sin": math.sin(wind_angle),
            "wind_dir_cos": math.cos(wind_angle),
            "dayofyear_sin": math.sin(day_angle),
            "dayofyear_cos": math.cos(day_angle),
            "songpu_flow_m3s": songpu_flow,
            "huangdu_flow_m3s": huangdu_flow,
            "songpu_water_level_m": songpu_level,
            "huangdu_water_level_m": huangdu_level,
            "songpu_flow_m3s_abs": abs(songpu_flow),
            "huangdu_flow_m3s_abs": abs(huangdu_flow),
            "songpu_flow_m3s_reverse_flag": 1.0 if songpu_flow < 0 else 0.0,
            "huangdu_flow_m3s_reverse_flag": 1.0 if huangdu_flow < 0 else 0.0,
            "songpu_flow_m3s_3d_mean": abs(songpu_flow),
            "songpu_flow_m3s_7d_mean": abs(songpu_flow),
            "huangdu_flow_m3s_3d_mean": abs(huangdu_flow),
            "huangdu_flow_m3s_7d_mean": abs(huangdu_flow),
            "songpu_water_level_m_1d_diff": self._finite(state.get("songpu_water_level_m_1d_diff", 0.0), 0.0),
            "songpu_water_level_m_3d_mean": songpu_level,
            "huangdu_water_level_m_1d_diff": self._finite(state.get("huangdu_water_level_m_1d_diff", 0.0), 0.0),
            "huangdu_water_level_m_3d_mean": huangdu_level,
            "songpu_flow_level_coupling": flow_level_coupling,
            "huangdu_flow_level_coupling": huangdu_flow * huangdu_level,
            "songpu_flow_m3s_1d_diff": self._finite(state.get("songpu_flow_m3s_1d_diff", 0.0), 0.0),
            "huangdu_flow_m3s_1d_diff": self._finite(state.get("huangdu_flow_m3s_1d_diff", 0.0), 0.0),
            "songpu_flow_rise_flag": self._finite(state.get("songpu_flow_rise_flag", 0.0), 0.0),
            "huangdu_flow_rise_flag": self._finite(state.get("huangdu_flow_rise_flag", 0.0), 0.0),
            "songpu_tidal_pumping_proxy": abs(flow_level_coupling),
            "songpu_resuspension_potential": abs(songpu_flow) * 0.05,
            "songpu_flushing_potential": abs(songpu_flow) * 0.05,
            "runoff_sediment_pulse": rainfall_3d * max(precipitation, 1.0),
        }

    def _finite(self, value: Any, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return numeric if math.isfinite(numeric) else default

