from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

from water_ai.data.multimodal_builder import _engineer_features
from water_ai.utils.io import ensure_dir, load_yaml, save_json

REALTIME_HOST = "https://naswater.market.alicloudapi.com"
REALTIME_STATIONS_PATH = "/api/stainfo/stations"
REALTIME_SNAPSHOT_PATH = "/api/stainfo/station_realtime"
DEFAULT_SECTION_NAME = "吴淞口"
DEFAULT_CHECK_SECTION_NAME = "张家浜"
REALTIME_PAGE_SIZE = 2000
CORE_REALTIME_MAPPING = {
    "water_temp": "water_temp",
    "ph": "ph",
    "dissolvedoxygen": "dissolved_oxygen",
    "conductivity": "conductivity",
    "turbidity": "turbidity",
    "codmn": "codmn",
    "nh3-n": "nh3_n",
    "tp": "tp",
    "tn": "tn",
}
CORE_FEATURES = list(CORE_REALTIME_MAPPING.values())
LATEST_BACKTEST_COUNT = 20
MODEL_CANDIDATES = ("cmfbe_stgcn", "mscim")
SENTINEL_VALUES = {"", "-", "-1", "-2", "null", "None"}


@dataclass(frozen=True)
class LatestValidationConfig:
    config_path: Path
    draft_path: Path
    outputs_root: Path
    artifact_root: Path
    section_name: str = DEFAULT_SECTION_NAME
    as_of_time: str | None = None
    check_section_name: str = DEFAULT_CHECK_SECTION_NAME


def _parse_appcode(draft_path: Path) -> str:
    for env_name in ("WATEREXPERT_REALTIME_APPCODE", "ALIYUN_APPCODE"):
        appcode = os.getenv(env_name, "").strip()
        if appcode:
            return appcode
    raw_bytes = draft_path.read_bytes()
    text = raw_bytes.decode("utf-8", errors="replace")
    for line in text.splitlines():
        normalized = line.replace("：", ":").strip()
        if normalized.lower().startswith("appcode:"):
            return normalized.split(":", 1)[1].strip()
    raise ValueError(f"Unable to find AppCode in {draft_path}")


def _fetch_json(path: str, params: dict[str, Any], appcode: str) -> dict[str, Any]:
    url = REALTIME_HOST + path
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"APPCODE {appcode}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
    return json.loads(payload)


def _coerce_realtime_container(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data", {})
    if isinstance(data, str):
        return json.loads(data)
    if isinstance(data, dict):
        return data
    raise TypeError("Realtime payload does not contain a JSON object in 'data'.")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in SENTINEL_VALUES:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


def _fetch_station_catalog(appcode: str) -> list[dict[str, Any]]:
    payload = _fetch_json(REALTIME_STATIONS_PATH, {}, appcode)
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise TypeError("Station catalog payload is not a list.")
    return rows


def _fetch_latest_snapshot(appcode: str, sta_time: str | None = None) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, Any] = {
        "pageNum": 1,
        "pageSize": REALTIME_PAGE_SIZE,
        "returnTotalNum": "true",
    }
    if sta_time:
        params["sta_time"] = sta_time
    payload = _fetch_json(REALTIME_SNAPSHOT_PATH, params, appcode)
    container = _coerce_realtime_container(payload)
    rows = container.get("rows", [])
    if not isinstance(rows, list):
        raise TypeError("Realtime snapshot rows payload is not a list.")
    return rows, int(container.get("totalNum") or len(rows))


def _station_lookup(stations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for station in stations:
        name = str(station.get("staname", "")).strip()
        if name and name not in lookup:
            lookup[name] = station
    return lookup


def _find_live_station_row(
    rows: list[dict[str, Any]],
    station_lookup: dict[str, dict[str, Any]],
    section_name: str,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    row = next((item for item in rows if str(item.get("section", "")).strip() == section_name), None)
    if row is None:
        raise ValueError(f"Realtime snapshot does not contain target section {section_name!r}.")
    station_meta = station_lookup.get(section_name)
    if station_meta is None:
        raise ValueError(f"Station catalog does not contain target section {section_name!r}.")
    lat = _safe_float(station_meta.get("latitude"))
    lon = _safe_float(station_meta.get("longitude"))
    if lat is None or lon is None:
        raise ValueError(f"Station catalog is missing coordinates for {section_name!r}.")
    distance_km = _haversine_km(31.392691, 121.522058, lat, lon)
    return row, station_meta, distance_km


def _section_rows(rows: list[dict[str, Any]], section_name: str) -> list[dict[str, Any]]:
    return [item for item in rows if str(item.get("section", "")).strip() == section_name]


def _station_access_check(
    stations: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    section_name: str,
) -> dict[str, Any]:
    catalog_matches = [
        station
        for station in stations
        if str(station.get("staname", "")).strip() == section_name
    ]
    realtime_matches = _section_rows(rows, section_name)
    realtime_rows = []
    for row in realtime_matches:
        present_fields = [
            target_key
            for source_key, target_key in CORE_REALTIME_MAPPING.items()
            if _safe_float(row.get(source_key)) is not None
        ]
        realtime_rows.append(
            {
                "section": str(row.get("section", "")).strip(),
                "monitor_time": str(row.get("monitor_time", "")).strip(),
                "present_field_count": len(present_fields),
                "required_field_count": len(CORE_REALTIME_MAPPING),
                "missing_fields": [
                    target_key
                    for target_key in CORE_REALTIME_MAPPING.values()
                    if target_key not in present_fields
                ],
                "is_complete": len(present_fields) == len(CORE_REALTIME_MAPPING),
            }
        )

    if realtime_rows:
        status = "complete" if any(row["is_complete"] for row in realtime_rows) else "incomplete"
    elif catalog_matches:
        status = "catalog_only"
    else:
        status = "not_found"
    return {
        "section_name": section_name,
        "status": status,
        "catalog_match_count": len(catalog_matches),
        "realtime_match_count": len(realtime_matches),
        "realtime_rows": realtime_rows,
        "note": (
            "当前国控站点目录和本次实时快照均未命中该断面名。"
            if status == "not_found"
            else ""
        ),
    }


def _load_historical_dataset(outputs_root: Path) -> pd.DataFrame:
    path = outputs_root / "intermediate" / "multimodal_daily_dataset.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _load_adjacency(outputs_root: Path) -> np.ndarray:
    path = outputs_root / "intermediate" / "feature_graph_adjacency.csv"
    return pd.read_csv(path, index_col=0).to_numpy(dtype=np.float32)


def _load_model_checkpoints(
    config_path: Path,
    outputs_root: Path,
) -> tuple[dict[str, torch.nn.Module], dict[str, Any]]:
    config = load_yaml(config_path)
    adjacency = _load_adjacency(outputs_root)
    checkpoints = {
        "mscim": torch.load(outputs_root / "models" / "mscim.pt", map_location="cpu"),
        "cmfbe_stgcn": torch.load(outputs_root / "models" / "cmfbe_stgcn.pt", map_location="cpu"),
    }
    meta = checkpoints["mscim"]["meta"]
    model_kwargs = {
        "num_features": len(meta["feature_columns"]),
        "adjacency": adjacency,
        "feature_index": meta["feature_index"],
        "clearness_log_min": float(meta["clearness_transform"]["log_turbidity_min"]),
        "clearness_log_max": float(meta["clearness_transform"]["log_turbidity_max"]),
        "hidden_dim": int(config["model"]["hidden_dim"]),
        "transformer_layers": int(config["model"]["transformer_layers"]),
        "num_heads": int(config["model"]["num_heads"]),
        "dropout": float(config["model"]["dropout"]),
        "max_sequence_length": int(meta["history_days"]),
    }

    from water_ai.models.mscim import MSCIMPrototype
    from water_ai.models.cmfbe_stgcn import CMFBE_STGCNPrototype

    models: dict[str, torch.nn.Module] = {
        "mscim": MSCIMPrototype(**model_kwargs),
        "cmfbe_stgcn": CMFBE_STGCNPrototype(**model_kwargs),
    }
    for model_name, model in models.items():
        model.load_state_dict(checkpoints[model_name]["state_dict"])
        model.eval()
    return models, meta


def _load_test_metrics(outputs_root: Path) -> dict[str, dict[str, float]]:
    frame = pd.read_csv(outputs_root / "metrics" / "model_comparison.csv")
    frame = frame[frame["split"] == "test"].copy()
    metrics: dict[str, dict[str, float]] = {}
    for row in frame.itertuples(index=False):
        metrics[row.model] = {
            "turbidity_rmse": float(row.turbidity_rmse),
            "turbidity_r2": float(row.turbidity_r2),
        }
    return metrics


def _build_live_observation(row: dict[str, Any]) -> dict[str, Any]:
    observation: dict[str, Any] = {
        "monitor_time": str(row.get("monitor_time", "")).strip(),
        "quality": str(row.get("quality", "")).strip(),
        "section_status": str(row.get("section_status", "")).strip(),
        "province": str(row.get("province", "")).strip(),
        "city": str(row.get("city", "")).strip(),
        "section": str(row.get("section", "")).strip(),
    }
    for source_key, target_key in CORE_REALTIME_MAPPING.items():
        observation[target_key] = _safe_float(row.get(source_key))
    return observation


def _available_features(historical_df: pd.DataFrame, live_observation: dict[str, Any]) -> list[str]:
    return [
        feature
        for feature in CORE_FEATURES
        if feature in historical_df.columns and live_observation.get(feature) is not None
    ]


def _valid_analog_candidates(df: pd.DataFrame, history_days: int) -> list[int]:
    valid_indices: list[int] = []
    dates = pd.to_datetime(df["date"]).reset_index(drop=True)
    for index in range(history_days - 1, len(df) - 1):
        start = index - history_days + 1
        if dates.iloc[index] - dates.iloc[start] == pd.Timedelta(days=history_days - 1):
            valid_indices.append(index)
    return valid_indices


def _rank_analog_candidates(
    historical_df: pd.DataFrame,
    live_observation: dict[str, Any],
    available_features: list[str],
    history_days: int,
) -> list[dict[str, Any]]:
    stats = historical_df[available_features].agg(["mean", "std"]).to_dict()
    ranked_rows: list[dict[str, Any]] = []
    for index in _valid_analog_candidates(historical_df, history_days):
        row = historical_df.iloc[index]
        components = []
        for feature in available_features:
            std_value = max(float(stats[feature]["std"]), 1e-6)
            delta = (float(live_observation[feature]) - float(row[feature])) / std_value
            components.append(delta ** 2)
        distance = float(math.sqrt(sum(components) / len(components)))
        ranked_rows.append(
            {
                "index": index,
                "date": str(pd.to_datetime(row["date"]).date()),
                "distance": distance,
                "turbidity": float(row["turbidity"]),
            }
        )
    return sorted(ranked_rows, key=lambda item: item["distance"])


def _build_scaler(historical_df: pd.DataFrame, feature_columns: list[str]) -> StandardScaler:
    scaler = StandardScaler()
    scaler.fit(historical_df[feature_columns])
    return scaler


def _build_inputs_from_window(
    window_df: pd.DataFrame,
    historical_df: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[torch.Tensor, torch.Tensor]:
    scaler = _build_scaler(historical_df, feature_columns)
    raw_values = window_df[feature_columns].to_numpy(dtype=np.float32)
    scaled_values = scaler.transform(window_df[feature_columns]).astype(np.float32)
    return (
        torch.tensor(scaled_values[np.newaxis, :, :], dtype=torch.float32),
        torch.tensor(raw_values[np.newaxis, :, :], dtype=torch.float32),
    )


def _predict_next_day_turbidity(
    model: torch.nn.Module,
    x: torch.Tensor,
    x_raw: torch.Tensor,
) -> float:
    with torch.no_grad():
        outputs = model(x, x_raw)
        return float(outputs["turbidity_pred"][0].item())


def _build_live_feature_window(
    historical_df: pd.DataFrame,
    analog: dict[str, Any],
    live_observation: dict[str, Any],
    feature_columns: list[str],
    history_days: int,
) -> pd.DataFrame:
    index = int(analog["index"])
    start = index - history_days + 1
    window_df = historical_df.iloc[start : index + 1].copy().reset_index(drop=True)
    live_timestamp = pd.to_datetime(live_observation["monitor_time"])
    last_index = len(window_df) - 1
    window_df.loc[last_index, "date"] = live_timestamp.normalize()
    for feature in CORE_FEATURES:
        if feature in window_df.columns and live_observation.get(feature) is not None:
            window_df.loc[last_index, feature] = float(live_observation[feature])

    engineered = _engineer_features(window_df)
    for feature in feature_columns:
        if feature not in engineered.columns:
            engineered[feature] = historical_df[feature].median()
    engineered[feature_columns] = (
        engineered[feature_columns]
        .apply(pd.to_numeric, errors="coerce")
        .interpolate(limit_direction="both")
        .ffill()
        .bfill()
    )
    return engineered


def _predict_live_next_day(
    historical_df: pd.DataFrame,
    top_analog: dict[str, Any],
    models: dict[str, torch.nn.Module],
    feature_columns: list[str],
    history_days: int,
    live_observation: dict[str, Any],
) -> dict[str, Any]:
    window_df = _build_live_feature_window(
        historical_df=historical_df,
        analog=top_analog,
        live_observation=live_observation,
        feature_columns=feature_columns,
        history_days=history_days,
    )
    x, x_raw = _build_inputs_from_window(window_df, historical_df, feature_columns)
    predictions = {
        model_name: _predict_next_day_turbidity(model, x, x_raw)
        for model_name, model in models.items()
    }
    live_timestamp = pd.to_datetime(live_observation["monitor_time"])
    return {
        "context_analog_date": top_analog["date"],
        "prediction_time": str(live_timestamp),
        "target_time": str(live_timestamp + pd.Timedelta(days=1)),
        "predictions": predictions,
    }


def _find_actual_target_observation(
    appcode: str,
    section_name: str,
    target_time: str,
) -> dict[str, Any] | None:
    rows, _ = _fetch_latest_snapshot(appcode, target_time)
    matches = _section_rows(rows, section_name)
    if not matches:
        return None
    return _build_live_observation(matches[0])


def _build_true_success_rate(
    live_prediction: dict[str, Any],
    actual_observation: dict[str, Any] | None,
    best_model_name: str,
    rmse_threshold: float,
) -> dict[str, Any] | None:
    if actual_observation is None or actual_observation.get("turbidity") is None:
        return None
    predicted_turbidity = float(live_prediction["predictions"][best_model_name])
    actual_turbidity = float(actual_observation["turbidity"])
    absolute_error = abs(predicted_turbidity - actual_turbidity)
    return {
        "best_model_name": best_model_name,
        "success_rate": 1.0 if absolute_error <= rmse_threshold else 0.0,
        "sample_count": 1,
        "rmse_threshold": float(rmse_threshold),
        "target_time": live_prediction["target_time"],
        "actual_monitor_time": actual_observation.get("monitor_time"),
        "actual_turbidity": actual_turbidity,
        "predicted_turbidity": predicted_turbidity,
        "absolute_error": float(absolute_error),
        "success": bool(absolute_error <= rmse_threshold),
    }


def _estimate_success_rate(
    historical_df: pd.DataFrame,
    ranked_candidates: list[dict[str, Any]],
    models: dict[str, torch.nn.Module],
    feature_columns: list[str],
    history_days: int,
    metrics_lookup: dict[str, dict[str, float]],
) -> dict[str, Any]:
    best_model_name = max(
        MODEL_CANDIDATES,
        key=lambda model_name: metrics_lookup[model_name]["turbidity_r2"],
    )
    rmse_threshold = metrics_lookup[best_model_name]["turbidity_rmse"]

    evaluation_rows: list[dict[str, Any]] = []
    for candidate in ranked_candidates[:LATEST_BACKTEST_COUNT]:
        index = int(candidate["index"])
        start = index - history_days + 1
        window_df = historical_df.iloc[start : index + 1].copy().reset_index(drop=True)
        actual_next_day = float(historical_df.iloc[index + 1]["turbidity"])
        x, x_raw = _build_inputs_from_window(window_df, historical_df, feature_columns)

        predictions = {
            model_name: _predict_next_day_turbidity(model, x, x_raw)
            for model_name, model in models.items()
        }
        best_prediction = predictions[best_model_name]
        absolute_error = abs(best_prediction - actual_next_day)
        evaluation_rows.append(
            {
                "analog_date": candidate["date"],
                "distance": float(candidate["distance"]),
                "actual_next_day_turbidity": actual_next_day,
                "predicted_next_day_turbidity": best_prediction,
                "absolute_error": absolute_error,
                "success": bool(absolute_error <= rmse_threshold),
                "mscim_prediction": predictions["mscim"],
                "cmfbe_prediction": predictions["cmfbe_stgcn"],
            }
        )

    success_rate = (
        sum(1 for row in evaluation_rows if row["success"]) / len(evaluation_rows)
        if evaluation_rows
        else 0.0
    )
    return {
        "best_model_name": best_model_name,
        "success_rate": float(success_rate),
        "sample_count": len(evaluation_rows),
        "rmse_threshold": float(rmse_threshold),
        "top_analog_backtests": evaluation_rows,
    }


def generate_latest_realtime_validation(config: LatestValidationConfig) -> dict[str, Any]:
    appcode = _parse_appcode(config.draft_path)
    stations = _fetch_station_catalog(appcode)
    latest_rows, total_latest_station_count = _fetch_latest_snapshot(appcode, config.as_of_time)
    station_lookup = _station_lookup(stations)
    live_row, station_meta, distance_km = _find_live_station_row(
        latest_rows,
        station_lookup,
        config.section_name,
    )
    historical_df = _load_historical_dataset(config.outputs_root)
    models, checkpoint_meta = _load_model_checkpoints(config.config_path, config.outputs_root)
    metrics_lookup = _load_test_metrics(config.outputs_root)

    live_observation = _build_live_observation(live_row)
    available_features = _available_features(historical_df, live_observation)
    ranked_candidates = _rank_analog_candidates(
        historical_df,
        live_observation,
        available_features,
        int(checkpoint_meta["history_days"]),
    )
    if not ranked_candidates:
        raise ValueError("Unable to find historical analog days for latest realtime observation.")

    success_estimate = _estimate_success_rate(
        historical_df,
        ranked_candidates,
        models,
        checkpoint_meta["feature_columns"],
        int(checkpoint_meta["history_days"]),
        metrics_lookup,
    )

    top_analog = ranked_candidates[0]
    live_timestamp = pd.to_datetime(live_observation["monitor_time"])
    live_prediction = _predict_live_next_day(
        historical_df,
        top_analog,
        models,
        checkpoint_meta["feature_columns"],
        int(checkpoint_meta["history_days"]),
        live_observation,
    )
    best_model_name = success_estimate["best_model_name"]
    target_actual = _find_actual_target_observation(
        appcode,
        config.section_name,
        live_prediction["target_time"],
    )
    true_success = _build_true_success_rate(
        live_prediction,
        target_actual,
        best_model_name,
        float(success_estimate["rmse_threshold"]),
    )
    if true_success is not None:
        success_rate = float(true_success["success_rate"])
        success_rate_title = "真实成功率"
        success_rate_type = "true"
        success_rate_note = (
            f"已回查 {true_success['actual_monitor_time']} 实测浊度 "
            f"{true_success['actual_turbidity']:.1f}；{best_model_name} 预测 "
            f"{true_success['predicted_turbidity']:.1f}，绝对误差 "
            f"{true_success['absolute_error']:.1f}，RMSE 判定阈值 "
            f"{true_success['rmse_threshold']:.1f}。"
        )
    else:
        success_rate = float(success_estimate["success_rate"])
        success_rate_title = "估计成功率"
        success_rate_type = "estimated"
        success_rate_note = (
            f"目标时刻 {live_prediction['target_time']} 的真实观测尚未可用；"
            f"当前显示基于最相似 {success_estimate['sample_count']} 个历史样本的回测估计。"
        )

    result = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "methodology": "realtime snapshot + historical analog context + true next-day validation when target observation exists",
        "snapshot_station_count": int(total_latest_station_count),
        "target_section": config.section_name,
        "requested_as_of_time": config.as_of_time,
        "latest_observation": {
            **live_observation,
            "distance_km_to_reference_station": round(distance_km, 3),
        },
        "summary_metrics": {
            "prediction_success_rate": success_rate,
            "prediction_success_rate_label": f"{round(success_rate * 100)}%",
            "prediction_success_rate_title": success_rate_title,
            "prediction_success_rate_type": success_rate_type,
            "prediction_success_rate_note": success_rate_note,
            "historical_similar_day": top_analog["date"],
            "historical_similar_day_note": f"与预测时刻状态最接近的历史样本日，距离 {top_analog['distance']:.3f}",
            "projected_target_date": str((live_timestamp.normalize() + pd.Timedelta(days=1)).date()),
            "projected_target_time": live_prediction["target_time"],
        },
        "analog_context": {
            "top_historical_similar_day": top_analog["date"],
            "analog_distance": float(top_analog["distance"]),
            "history_days": int(checkpoint_meta["history_days"]),
            "available_features": available_features,
        },
        "live_prediction": live_prediction,
        "target_actual_observation": target_actual,
        "true_success_rate": true_success,
        "success_estimate": success_estimate,
        "station_access_checks": {
            config.check_section_name: _station_access_check(
                stations,
                latest_rows,
                config.check_section_name,
            )
        },
    }

    artifact_root = ensure_dir(config.artifact_root)
    save_json(result, artifact_root / "latest_validation.json")
    pd.DataFrame(success_estimate["top_analog_backtests"]).to_csv(
        artifact_root / "latest_validation_backtests.csv",
        index=False,
        encoding="utf-8-sig",
    )
    return result
