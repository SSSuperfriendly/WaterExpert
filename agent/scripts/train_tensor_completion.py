from __future__ import annotations

import argparse
from pathlib import Path

from water_ai.tech_kb.tensor_complete import TensorCompletion


DEFAULT_TENSOR_PATH = Path("data/tech_knowledge_base/applicability_tensor.npz")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Complete the technology applicability tensor.")
    parser.add_argument("--tensor-path", type=Path, default=DEFAULT_TENSOR_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--rank", type=int, default=4)
    parser.add_argument("--max-iter", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trainer = TensorCompletion(args.tensor_path, rank=args.rank, max_iter=args.max_iter)
    observed, mask, _ = trainer.load()
    output_path = trainer.save_completed(args.output)
    print(f"Loaded tensor shape: {observed.shape}")
    print(f"Observed entries: {int(mask.sum())}/{mask.size}")
    print(f"Completed tensor saved: {output_path}")


if __name__ == "__main__":
    main()
