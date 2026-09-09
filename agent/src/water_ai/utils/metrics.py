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
