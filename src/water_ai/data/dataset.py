from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset


class TimeSeriesWindowDataset(Dataset):
    def __init__(
        self,
        df: pd.DataFrame,
        feature_columns: list[str],
        scaler: StandardScaler,
        history_days: int,
        horizon_days: int,
    ) -> None:
        self.feature_columns = feature_columns
        self.samples: list[dict[str, np.ndarray | float | str]] = []

        raw_features = df[feature_columns].to_numpy(dtype=np.float32)
        scaled_features = scaler.transform(df[feature_columns]).astype(np.float32)
        turbidity = df["turbidity"].to_numpy(dtype=np.float32)
        log_turbidity = np.log1p(np.clip(turbidity, a_min=0.0, a_max=None)).astype(np.float32)
        clearness = df["clearness_proxy"].to_numpy(dtype=np.float32)
        dates = pd.to_datetime(df["date"]).reset_index(drop=True)

        total_needed = history_days + horizon_days
        for start in range(0, len(df) - total_needed + 1):
            end = start + history_days
            target_index = end + horizon_days - 1
            if dates.iloc[target_index] - dates.iloc[start] != pd.Timedelta(days=total_needed - 1):
                continue

            self.samples.append(
                {
                    "x": scaled_features[start:end],
                    "x_raw": raw_features[start:end],
                    "last_turbidity": float(turbidity[end - 1]),
                    "last_clearness": float(clearness[end - 1]),
                    "y_turbidity": float(turbidity[target_index]),
                    "y_log_turbidity": float(log_turbidity[target_index]),
                    "y_clearness": float(clearness[target_index]),
                    "target_date": dates.iloc[target_index].strftime("%Y-%m-%d"),
                }
            )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor | str]:
        sample = self.samples[index]
        return {
            "x": torch.tensor(sample["x"], dtype=torch.float32),
            "x_raw": torch.tensor(sample["x_raw"], dtype=torch.float32),
            "last_turbidity": torch.tensor(sample["last_turbidity"], dtype=torch.float32),
            "last_clearness": torch.tensor(sample["last_clearness"], dtype=torch.float32),
            "y_turbidity": torch.tensor(sample["y_turbidity"], dtype=torch.float32),
            "y_log_turbidity": torch.tensor(sample["y_log_turbidity"], dtype=torch.float32),
            "y_clearness": torch.tensor(sample["y_clearness"], dtype=torch.float32),
            "target_date": sample["target_date"],
        }


@dataclass
class PreparedData:
    train_loader: DataLoader
    val_loader: DataLoader
    test_loader: DataLoader
    scaler: StandardScaler
    feature_columns: list[str]
    feature_index: dict[str, int]
    split_summary: dict[str, str | int]


def _split_dataframe(df: pd.DataFrame, train_ratio: float, val_ratio: float) -> tuple[pd.DataFrame, ...]:
    df = df.sort_values("date").reset_index(drop=True)
    total_rows = len(df)
    train_end = int(total_rows * train_ratio)
    val_end = int(total_rows * (train_ratio + val_ratio))

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()
    return train_df, val_df, test_df


def prepare_dataloaders(
    df: pd.DataFrame,
    feature_columns: list[str],
    history_days: int,
    horizon_days: int,
    train_ratio: float,
    val_ratio: float,
    batch_size: int,
) -> PreparedData:
    train_df, val_df, test_df = _split_dataframe(df, train_ratio=train_ratio, val_ratio=val_ratio)

    scaler = StandardScaler()
    scaler.fit(train_df[feature_columns])

    train_dataset = TimeSeriesWindowDataset(
        train_df, feature_columns, scaler, history_days=history_days, horizon_days=horizon_days
    )
    val_dataset = TimeSeriesWindowDataset(
        val_df, feature_columns, scaler, history_days=history_days, horizon_days=horizon_days
    )
    test_dataset = TimeSeriesWindowDataset(
        test_df, feature_columns, scaler, history_days=history_days, horizon_days=horizon_days
    )

    return PreparedData(
        train_loader=DataLoader(train_dataset, batch_size=batch_size, shuffle=True),
        val_loader=DataLoader(val_dataset, batch_size=batch_size, shuffle=False),
        test_loader=DataLoader(test_dataset, batch_size=batch_size, shuffle=False),
        scaler=scaler,
        feature_columns=feature_columns,
        feature_index={feature: idx for idx, feature in enumerate(feature_columns)},
        split_summary={
            "train_rows": int(len(train_df)),
            "val_rows": int(len(val_df)),
            "test_rows": int(len(test_df)),
            "train_windows": int(len(train_dataset)),
            "val_windows": int(len(val_dataset)),
            "test_windows": int(len(test_dataset)),
            "train_start": str(train_df["date"].min().date()),
            "train_end": str(train_df["date"].max().date()),
            "val_start": str(val_df["date"].min().date()),
            "val_end": str(val_df["date"].max().date()),
            "test_start": str(test_df["date"].min().date()),
            "test_end": str(test_df["date"].max().date()),
        },
    )
