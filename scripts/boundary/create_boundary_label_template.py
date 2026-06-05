from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.data.multimodal_builder import build_multimodal_dataset
from water_ai.utils.io import load_yaml


def main() -> None:
    config = load_yaml(PROJECT_ROOT / "configs" / "prototype_repo.yaml")
    hydrodynamics_config = config.get("hydrodynamics", {})
    ndti_config = config.get("ndti", {})
    dataset_df, _ = build_multimodal_dataset(
        data_root=config["data_root"],
        water_pattern=config["water_pattern"],
        weather_filename=config["weather_filename"],
        output_dir=PROJECT_ROOT / "outputs",
        hydrodynamics_enabled=bool(hydrodynamics_config.get("enabled", False)),
        hydrodynamics_source_path=hydrodynamics_config.get("source_path"),
        hydrodynamics_wide_path=hydrodynamics_config.get("wide_path"),
        hydrodynamics_output_dir=hydrodynamics_config.get("output_dir"),
        ndti_enabled=bool(ndti_config.get("enabled", False)),
        ndti_dir=ndti_config.get("source_dir"),
        ndti_output_dir=ndti_config.get("output_dir"),
        boundary_config={"enabled": False},
    )

    template = pd.DataFrame(
        {
            "date": pd.to_datetime(dataset_df["date"]).dt.strftime("%Y-%m-%d"),
            "boundary_label": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "boundary_extent_ratio": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "label_source": "",
            "label_confidence": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "boundary_zone_name": "",
            "notes": "",
        }
    )
    output_path = PROJECT_ROOT / "data" / "raw" / "wusongkou_boundary_labels_template.csv"
    template.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved boundary label template: {output_path}")


if __name__ == "__main__":
    main()
