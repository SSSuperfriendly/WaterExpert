from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.feature_selection import SelectKBest, f_regression
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "zhangjiabang_cross_modal"

TARGETS = {
    "turbidity_ntu": {
        "label": "turbidity",
        "unit": "NTU",
        "absolute_success_tolerance": 20.0,
        "relative_success_tolerance": 0.20,
    },
    "secchi_depth_m": {
        "label": "secchi_depth",
        "unit": "m",
        "absolute_success_tolerance": 0.08,
        "relative_success_tolerance": 0.25,
    },
}

NON_VISUAL_FEATURES = [
    "sample_day_index",
    "sample_dayofyear_sin",
    "sample_dayofyear_cos",
    "sample_month",
    "sample_day",
    "weather_pressure",
    "weather_air_temp",
    "weather_humidity",
    "weather_precipitation",
    "weather_wind_speed",
    "weather_wind_dir",
]

VISUAL_STAT_FEATURES = [
    "uav_asset_count",
    "uav_image_count",
    "uav_video_count",
    "uav_brightness_mean_mean",
    "uav_saturation_mean_mean",
    "uav_green_index_mean",
    "uav_brown_yellow_index_mean",
    "uav_dark_water_ratio_mean",
    "uav_high_glare_ratio_mean",
    "uav_vegetation_like_ratio_mean",
    "uav_turbidity_visual_proxy_mean",
    "uav_sharpness_laplacian_mean",
]

MODEL_SPECS = {
    "baseline_non_visual": {
        "display_name": "加入跨模态前",
        "feature_groups": ["non_visual_context"],
        "description": "Only date context and available proxy weather fields are used.",
    },
    "cross_modal_visual_stats": {
        "display_name": "加入可解释视觉特征后",
        "feature_groups": ["non_visual_context", "uav_visual_statistics"],
        "description": "Adds UAV color, texture, glare, vegetation, and visual turbidity proxy features.",
    },
    "cross_modal_transformer": {
        "display_name": "加入Transformer视觉表征后",
        "feature_groups": [
            "non_visual_context",
            "uav_visual_statistics",
            "uav_transformer_embeddings",
        ],
        "description": "Adds date-aligned UAV visual statistics plus patch-Transformer embedding features.",
    },
}


def add_date_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    sample_dates = pd.to_datetime(result["sample_date"])
    start = sample_dates.min()
    result["sample_day_index"] = (sample_dates - start).dt.days.astype(float)
    dayofyear = sample_dates.dt.dayofyear.astype(float)
    result["sample_dayofyear_sin"] = np.sin(2 * np.pi * dayofyear / 366.0)
    result["sample_dayofyear_cos"] = np.cos(2 * np.pi * dayofyear / 366.0)
    result["sample_month"] = sample_dates.dt.month.astype(float)
    result["sample_day"] = sample_dates.dt.day.astype(float)
    return result


def supervised_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "has_field_monitoring_label" in df.columns:
        supervised = df[df["has_field_monitoring_label"].astype(bool)].copy()
    else:
        supervised = df.iloc[0:0].copy()
    if supervised.empty:
        supervised = df[df["turbidity_ntu"].notna() | df["secchi_depth_m"].notna()].copy()
    return supervised


def _numeric_existing_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [
        column
        for column in columns
        if column in df.columns
        and pd.api.types.is_numeric_dtype(df[column])
        and pd.to_numeric(df[column], errors="coerce").notna().any()
    ]


def _transformer_columns(df: pd.DataFrame) -> list[str]:
    return [
        column
        for column in df.columns
        if "visual_transformer_embedding_" in column
        and column.endswith("_mean")
        and pd.api.types.is_numeric_dtype(df[column])
        and pd.to_numeric(df[column], errors="coerce").notna().any()
    ]


def feature_sets(df: pd.DataFrame) -> dict[str, list[str]]:
    non_visual = _numeric_existing_columns(df, NON_VISUAL_FEATURES)
    visual_stats = _numeric_existing_columns(df, VISUAL_STAT_FEATURES)
    transformer = _transformer_columns(df)
    return {
        "baseline_non_visual": non_visual,
        "cross_modal_visual_stats": [*non_visual, *visual_stats],
        "cross_modal_transformer": [*non_visual, *visual_stats, *transformer],
    }


def _safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denominator = np.maximum(np.abs(y_true), 1e-6)
    return float(np.mean(np.abs((y_true - y_pred) / denominator)) * 100.0)


def _success_rate(target: str, y_true: np.ndarray, y_pred: np.ndarray) -> float:
    spec = TARGETS[target]
    absolute = float(spec["absolute_success_tolerance"])
    relative = float(spec["relative_success_tolerance"])
    tolerance = np.maximum(absolute, relative * np.abs(y_true))
    return float(np.mean(np.abs(y_true - y_pred) <= tolerance))


def _build_model(train_rows: int, feature_count: int) -> Pipeline:
    steps: list[tuple[str, Any]] = [
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ]
    if feature_count > max(train_rows, 6):
        k = min(3, max(1, train_rows - 1), feature_count)
        steps.append(("select", SelectKBest(score_func=f_regression, k=k)))
        max_components = min(2, train_rows - 1, k)
        if max_components >= 1 and k > max_components:
            steps.append(("pca", PCA(n_components=max_components, random_state=20260817)))
    steps.append(("ridge", Ridge(alpha=5.0)))
    return Pipeline(steps)


def _leave_one_out_predictions(
    df: pd.DataFrame,
    *,
    target: str,
    model_name: str,
    features: list[str],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    y = pd.to_numeric(df[target], errors="coerce").astype(float).to_numpy()
    x = df[features].apply(pd.to_numeric, errors="coerce").astype(float).to_numpy()
    predictions = np.zeros_like(y, dtype=float)
    rows: list[dict[str, Any]] = []
    for holdout in range(len(df)):
        train_mask = np.ones(len(df), dtype=bool)
        train_mask[holdout] = False
        model = _build_model(int(train_mask.sum()), len(features))
        model.fit(x[train_mask], y[train_mask])
        prediction = float(model.predict(x[[holdout]])[0])
        predictions[holdout] = prediction
        rows.append(
            {
                "sample_date": df.iloc[holdout]["sample_date"],
                "field_sample_date": df.iloc[holdout].get("field_sample_date", ""),
                "target": target,
                "model_name": model_name,
                "actual": float(y[holdout]),
                "predicted": prediction,
                "absolute_error": abs(float(y[holdout]) - prediction),
                "label_alignment": df.iloc[holdout].get("label_alignment", ""),
                "fusion_readiness": df.iloc[holdout].get("fusion_readiness", ""),
                "feature_count": len(features),
                "cv_strategy": "leave_one_out",
            }
        )
    return predictions, rows


def evaluate_cross_modal_models(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prepared = add_date_features(supervised_rows(df))
    all_feature_sets = feature_sets(prepared)
    metric_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    for target in TARGETS:
        target_df = prepared[prepared[target].notna()].copy().reset_index(drop=True)
        if len(target_df) < 3:
            continue
        for model_name, features in all_feature_sets.items():
            if not features:
                continue
            y_true = pd.to_numeric(target_df[target], errors="coerce").astype(float).to_numpy()
            y_pred, rows = _leave_one_out_predictions(
                target_df,
                target=target,
                model_name=model_name,
                features=features,
            )
            prediction_rows.extend(rows)
            metric_rows.append(
                {
                    "target": target,
                    "target_label": TARGETS[target]["label"],
                    "unit": TARGETS[target]["unit"],
                    "model_name": model_name,
                    "display_name": MODEL_SPECS[model_name]["display_name"],
                    "feature_groups": ";".join(MODEL_SPECS[model_name]["feature_groups"]),
                    "feature_count": len(features),
                    "sample_count": len(target_df),
                    "cv_strategy": "leave_one_out",
                    "mae": float(mean_absolute_error(y_true, y_pred)),
                    "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
                    "r2": float(r2_score(y_true, y_pred)),
                    "mape": _safe_mape(y_true, y_pred),
                    "success_rate": _success_rate(target, y_true, y_pred),
                    "description": MODEL_SPECS[model_name]["description"],
                }
            )
    metrics = pd.DataFrame(metric_rows)
    predictions = pd.DataFrame(prediction_rows)
    _attach_baseline_deltas(metrics)
    return metrics, predictions


def _attach_baseline_deltas(metrics: pd.DataFrame) -> None:
    if metrics.empty:
        return
    baseline_by_target = (
        metrics[metrics["model_name"] == "baseline_non_visual"]
        .set_index("target")
        .to_dict(orient="index")
    )
    for index, row in metrics.iterrows():
        baseline = baseline_by_target.get(row["target"])
        if not baseline:
            continue
        metrics.loc[index, "rmse_delta_vs_baseline"] = row["rmse"] - baseline["rmse"]
        metrics.loc[index, "rmse_reduction_pct_vs_baseline"] = (
            (baseline["rmse"] - row["rmse"]) / baseline["rmse"] * 100.0
            if baseline["rmse"]
            else 0.0
        )
        metrics.loc[index, "success_rate_delta_vs_baseline"] = (
            row["success_rate"] - baseline["success_rate"]
        )


def evaluation_summary(metrics: pd.DataFrame, predictions: pd.DataFrame) -> dict[str, Any]:
    targets: dict[str, Any] = {}
    for target, group in metrics.groupby("target"):
        ordered = group.sort_values("rmse", ascending=True)
        best = ordered.iloc[0].to_dict()
        baseline = group[group["model_name"] == "baseline_non_visual"]
        targets[target] = {
            "best_model": best["model_name"],
            "best_display_name": best["display_name"],
            "best_rmse": best["rmse"],
            "best_success_rate": best["success_rate"],
            "baseline_rmse": float(baseline.iloc[0]["rmse"]) if not baseline.empty else None,
            "rows": group.to_dict(orient="records"),
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site": "张家浜",
        "evaluation_scope": "same supervised Zhangjiabang cross-modal rows",
        "cv_strategy": "leave_one_out",
        "sample_count": int(metrics["sample_count"].max()) if not metrics.empty else 0,
        "targets": targets,
        "metric_rows": metrics.to_dict(orient="records"),
        "prediction_rows": predictions.to_dict(orient="records"),
        "notes": [
            "This is a small-sample model comparison, not a production retraining benchmark.",
            "Baseline uses non-visual date/proxy context; cross-modal variants add UAV visual features.",
            "Success rate uses target-specific tolerances recorded in this module.",
        ],
    }


def write_evaluation_outputs(
    output_dir: Path,
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_options = {"index": False, "encoding": "utf-8-sig", "lineterminator": "\n"}
    metrics_path = output_dir / "cross_modal_model_comparison.csv"
    predictions_path = output_dir / "cross_modal_model_predictions.csv"
    summary_path = output_dir / "cross_modal_model_comparison.json"
    metrics.to_csv(metrics_path, **csv_options)
    predictions.to_csv(predictions_path, **csv_options)
    summary = evaluation_summary(metrics, predictions)
    summary["outputs"] = {
        "metrics_csv": metrics_path.relative_to(PROJECT_ROOT).as_posix(),
        "predictions_csv": predictions_path.relative_to(PROJECT_ROOT).as_posix(),
        "summary_json": summary_path.relative_to(PROJECT_ROOT).as_posix(),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def evaluate_and_write(input_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    if "sample_date" not in df.columns:
        raise ValueError("Input cross-modal table must include sample_date.")
    metrics, predictions = evaluate_cross_modal_models(df)
    if metrics.empty:
        raise ValueError("Not enough supervised Zhangjiabang rows to evaluate models.")
    return write_evaluation_outputs(output_dir, metrics, predictions)
