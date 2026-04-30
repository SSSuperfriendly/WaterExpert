from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from water_ai.utils.io import ensure_dir, save_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge preprocessed hydrodynamics with the existing multimodal daily dataset."
    )
    parser.add_argument(
        "--base-dataset",
        type=str,
        default="G:\\AI4S\\mscim_cmfbe_prototype\\outputs\\intermediate\\multimodal_daily_dataset.csv",
    )
    parser.add_argument(
        "--hydro-dataset",
        type=str,
        default="G:\\AI4S\\mscim_cmfbe_prototype\\outputs\\hydrodynamics_preprocessed\\shanghai_hydrodynamics_daily_wide.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="G:\\AI4S\\mscim_cmfbe_prototype\\outputs\\intermediate",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = ensure_dir(args.output_dir)

    base_df = pd.read_csv(args.base_dataset, parse_dates=["date"]).sort_values("date")
    hydro_df = pd.read_csv(args.hydro_dataset, parse_dates=["date"]).sort_values("date")

    merged_df = pd.merge(base_df, hydro_df, on="date", how="inner")
    merged_df = merged_df.sort_values("date").reset_index(drop=True)

    # Add a few merge-ready interaction features for diagnosis and transport simulation.
    if {"turbidity", "songpu_flow_m3s_abs"}.issubset(merged_df.columns):
        merged_df["turbidity_songpu_flow_interaction"] = (
            merged_df["turbidity"].fillna(0.0) * merged_df["songpu_flow_m3s_abs"].fillna(0.0)
        )
    if {"turbidity", "songpu_water_level_m_1d_diff"}.issubset(merged_df.columns):
        merged_df["turbidity_songpu_level_jump_interaction"] = (
            merged_df["turbidity"].fillna(0.0)
            * merged_df["songpu_water_level_m_1d_diff"].abs().fillna(0.0)
        )
    if {"conductivity", "songpu_flow_m3s_reverse_flag"}.issubset(merged_df.columns):
        merged_df["conductivity_backflow_interaction"] = (
            merged_df["conductivity"].fillna(0.0)
            * merged_df["songpu_flow_m3s_reverse_flag"].fillna(0.0)
        )

    output_path = output_dir / "multimodal_daily_dataset_with_hydrodynamics.csv"
    merged_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    summary = {
        "base_dataset": str(args.base_dataset),
        "hydrodynamics_dataset": str(args.hydro_dataset),
        "output_dataset": str(output_path),
        "rows": int(len(merged_df)),
        "date_range": {
            "start": str(merged_df["date"].min().date()),
            "end": str(merged_df["date"].max().date()),
        },
        "added_hydrodynamic_columns": [
            column
            for column in hydro_df.columns
            if column != "date" and column in merged_df.columns
        ],
        "added_cross_features": [
            column
            for column in [
                "turbidity_songpu_flow_interaction",
                "turbidity_songpu_level_jump_interaction",
                "conductivity_backflow_interaction",
            ]
            if column in merged_df.columns
        ],
        "notes": {
            "merge_key": "date",
            "merge_type": "inner",
            "reason": "Only the overlapping period is kept so the dataset is immediately trainable.",
        },
    }
    save_json(summary, output_dir / "multimodal_hydrodynamics_merge_summary.json")

    print(f"Saved: {output_path}")
    print(f"Saved: {output_dir / 'multimodal_hydrodynamics_merge_summary.json'}")


if __name__ == "__main__":
    main()
