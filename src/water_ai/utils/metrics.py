from __future__ import annotations

import math
from typing import Iterable

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def regression_metrics(y_true: Iterable[float], y_pred: Iterable[float]) -> dict[str, float]:
    y_true_arr = np.asarray(list(y_true), dtype=float)
    y_pred_arr = np.asarray(list(y_pred), dtype=float)
    if y_true_arr.size == 0:
        return {"mae": math.nan, "rmse": math.nan, "r2": math.nan, "mape": math.nan}

    denom = np.where(np.abs(y_true_arr) < 1e-6, 1.0, np.abs(y_true_arr))
    mape = float(np.mean(np.abs((y_true_arr - y_pred_arr) / denom)) * 100.0)

    return {
        "mae": float(mean_absolute_error(y_true_arr, y_pred_arr)),
        "rmse": float(np.sqrt(mean_squared_error(y_true_arr, y_pred_arr))),
        "r2": float(r2_score(y_true_arr, y_pred_arr)),
        "mape": mape,
    }


def binary_classification_metrics(
    y_true: Iterable[float], y_prob: Iterable[float], threshold: float = 0.5
) -> dict[str, float]:
    y_true_arr = np.asarray(list(y_true), dtype=float)
    y_prob_arr = np.asarray(list(y_prob), dtype=float)
    if y_true_arr.size == 0:
        return {
            "accuracy": math.nan,
            "precision": math.nan,
            "recall": math.nan,
            "f1": math.nan,
            "positive_rate": math.nan,
        }

    y_pred_arr = (y_prob_arr >= threshold).astype(int)
    y_true_bin = (y_true_arr >= 0.5).astype(int)

    tp = int(np.sum((y_pred_arr == 1) & (y_true_bin == 1)))
    fp = int(np.sum((y_pred_arr == 1) & (y_true_bin == 0)))
    fn = int(np.sum((y_pred_arr == 0) & (y_true_bin == 1)))
    tn = int(np.sum((y_pred_arr == 0) & (y_true_bin == 0)))

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2.0 * precision * recall / max(1e-12, precision + recall)
    accuracy = (tp + tn) / max(1, tp + tn + fp + fn)

    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "positive_rate": float(np.mean(y_true_bin)),
    }
