from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from water_ai.data.loader import WaterQualityDataLoader
from water_ai.rl.trainer import RLTrainer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the RL-TGRR policy locally.")
    parser.add_argument("--steps", "--timesteps", dest="steps", type=int, default=10000)
    parser.add_argument("--scenario", default="s1", help="Accepted for QUICKSTART compatibility.")
    parser.add_argument("--save-interval", "--save-freq", dest="save_interval", type=int, default=1000)
    parser.add_argument("--log-interval", dest="log_interval", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output-dir", default="outputs/policy")
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Run the lightweight internal trainer instead of Stable-Baselines3.",
    )
    return parser.parse_args()


def run_stub_training(output_dir: Path) -> dict[str, object]:
    trainer = RLTrainer(config={"env": {"horizon": 5}, "algorithm": {"gamma": 0.99}})
    result = trainer.train(episodes=1)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "training_stub_summary.json"
    summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {"status": "stub", "summary_path": str(summary_path), **result}


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    if args.stub:
        result = run_stub_training(output_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    try:
        from train_rl_tgrr_complete import RLTGRRTrainer
    except Exception as exc:
        print(f"Stable training stack unavailable ({exc}); falling back to --stub behavior.")
        result = run_stub_training(output_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"Training RL-TGRR for {args.steps} timesteps on scenario hint {args.scenario}.")
    loader = WaterQualityDataLoader(target_station=2586)
    trainer = RLTGRRTrainer(
        data_loader=loader,
        output_dir=args.output_dir,
        config={
            "learning_rate": args.learning_rate,
            "batch_size": args.batch_size,
            "device": args.device,
        },
    )
    result = trainer.train(total_timesteps=args.steps, save_freq=args.save_interval)

    if result.get("status") == "success":
        checkpoints_dir = Path(result["checkpoints_dir"])
        latest_path = checkpoints_dir / "latest.zip"
        best_path = checkpoints_dir / "best.zip"
        if latest_path.exists():
            shutil.copyfile(latest_path, best_path)
            result["best_policy_path"] = str(best_path)
        print("Training complete.")
    else:
        print("Training failed.")

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
