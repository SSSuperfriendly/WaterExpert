from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.data.hydrodynamics import (
    DEFAULT_XLS_FILENAME,
    preprocess_hydrodynamics_xls,
    resolve_hydrodynamics_xls,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess Shanghai hydrodynamics xls into tidy daily tables."
    )
    parser.add_argument(
        "--input",
        type=str,
        default=str(PROJECT_ROOT / "data" / "raw" / DEFAULT_XLS_FILENAME),
        help="Source xls path. Defaults to the repository-local raw hydrodynamics file.",
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default=str(PROJECT_ROOT / "data" / "raw"),
        help="Directory used for fallback xls discovery.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "outputs" / "hydrodynamics_preprocessed"),
        help="Directory to save cleaned outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    xls_path = resolve_hydrodynamics_xls(args.data_root, args.input)
    _, _, summary = preprocess_hydrodynamics_xls(xls_path=xls_path, output_dir=args.output_dir)

    print(f"Saved long/wide hydrodynamics tables to: {args.output_dir}")
    print(
        "Date range: "
        f"{summary['date_range']['start']} to {summary['date_range']['end']} "
        f"({summary['wide_rows']} daily rows)"
    )


if __name__ == "__main__":
    main()
