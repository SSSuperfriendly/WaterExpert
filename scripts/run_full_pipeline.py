from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.linear_model import Ridge

from water_ai.data.dataset import PreparedData, prepare_dataloaders
from water_ai.data.kg_priors import build_feature_graph_priors
from water_ai.data.multimodal_builder import build_multimodal_dataset
from water_ai.interpretability.turbidity_diagnosis import diagnose_mscim_turbidity
from water_ai.models.cmfbe_stgcn import CMFBE_STGCNPrototype
from water_ai.models.mscim import MSCIMPrototype
from water_ai.physics.equations import export_physics_note
from water_ai.utils.io import ensure_dir, load_yaml, save_json, set_seed
from water_ai.utils.metrics import regression_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MSCIM/CMFBE prototype pipeline.")
    parser.add_argument(
        "--config",
        type=str,
        default=str(PROJECT_ROOT / "configs" / "prototype_repo.yaml"),
        help="Path to the YAML config file.",
    )
    return parser.parse_args()


def choose_device(config_device: str) -> torch.device:
    if config_device == "cpu":
        return torch.device("cpu")
    if config_device == "cuda":
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def move_batch(batch: dict[str, Any], device: torch.device) -> dict[str, Any]:
    moved = {}
    for key, value in batch.items():
        moved[key] = value.to(device) if torch.is_tensor(value) else value
    return moved


def compute_loss(
    outputs: dict[str, torch.Tensor],
    batch: dict[str, torch.Tensor],
    clearness_weight: float,
    physics_weight: float,
    change_weight: float,
    mechanism_weight: float,
    risk_weight: float,
    include_physics: bool,
) -> torch.Tensor:
    loss = F.smooth_l1_loss(outputs["log_turbidity_pred"], batch["y_log_turbidity"])
    loss = loss + clearness_weight * F.mse_loss(outputs["clearness_pred"], batch["y_clearness"])
    baseline_log_turbidity = torch.log1p(torch.clamp(batch["last_turbidity"], min=0.0))
    target_delta_log_turbidity = batch["y_log_turbidity"] - baseline_log_turbidity
    pred_delta_log_turbidity = outputs["log_turbidity_pred"] - baseline_log_turbidity
    loss = loss + change_weight * F.smooth_l1_loss(
        pred_delta_log_turbidity, target_delta_log_turbidity
    )
    loss = loss + change_weight * clearness_weight * F.mse_loss(
        outputs["clearness_pred"] - batch["last_clearness"],
        batch["y_clearness"] - batch["last_clearness"],
    )
    if risk_weight > 0.0:
        loss = loss + risk_weight * F.binary_cross_entropy_with_logits(
            outputs["self_purification_failure_logit"],
            batch["y_self_purification_failure"],
        )
        loss = loss + risk_weight * F.binary_cross_entropy_with_logits(
            outputs["turbidity_surge_logit"],
            batch["y_turbidity_surge"],
        )
        loss = loss + risk_weight * F.binary_cross_entropy_with_logits(
            outputs["critical_transition_logit"],
            batch["y_critical_transition"],
        )
    if include_physics and "physics_turbidity_pred" in outputs:
        physics_log_turbidity_pred = outputs.get(
            "physics_log_turbidity_pred", torch.log1p(outputs["physics_turbidity_pred"])
        )
        loss = loss + physics_weight * F.smooth_l1_loss(
            physics_log_turbidity_pred, batch["y_log_turbidity"]
        )
        if "physics_delta_log_turbidity" in outputs:
            loss = loss + mechanism_weight * F.smooth_l1_loss(
                outputs["physics_delta_log_turbidity"], target_delta_log_turbidity
            )
    return loss


def run_epoch(
    model: torch.nn.Module,
    loader: torch.utils.data.DataLoader,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    clearness_weight: float,
    physics_weight: float,
    change_weight: float,
    mechanism_weight: float,
    risk_weight: float,
    include_physics: bool,
) -> float:
    model.train() if optimizer is not None else model.eval()
    losses = []

    for batch in loader:
        batch = move_batch(batch, device)
        if optimizer is not None:
            optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(optimizer is not None):
            outputs = model(batch["x"], batch["x_raw"])
            loss = compute_loss(
                outputs=outputs,
                batch=batch,
                clearness_weight=clearness_weight,
                physics_weight=physics_weight,
                change_weight=change_weight,
                mechanism_weight=mechanism_weight,
                risk_weight=risk_weight,
                include_physics=include_physics,
            )
            if optimizer is not None:
                loss.backward()
                optimizer.step()
        losses.append(float(loss.detach().cpu().item()))

    return float(np.mean(losses)) if losses else float("nan")


def train_model(
    model: torch.nn.Module,
    prepared: PreparedData,
    device: torch.device,
    epochs: int,
    learning_rate: float,
    weight_decay: float,
    clearness_weight: float,
    physics_weight: float,
    change_weight: float,
    mechanism_weight: float,
    risk_weight: float,
    include_physics: bool,
) -> tuple[torch.nn.Module, list[dict[str, float]]]:
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )
    history: list[dict[str, float]] = []
    best_state = copy.deepcopy(model.state_dict())
    best_val = float("inf")

    for epoch in range(1, epochs + 1):
        train_loss = run_epoch(
            model=model,
            loader=prepared.train_loader,
            optimizer=optimizer,
            device=device,
            clearness_weight=clearness_weight,
            physics_weight=physics_weight,
            change_weight=change_weight,
            mechanism_weight=mechanism_weight,
            risk_weight=risk_weight,
            include_physics=include_physics,
        )
        val_loss = run_epoch(
            model=model,
            loader=prepared.val_loader,
            optimizer=None,
            device=device,
            clearness_weight=clearness_weight,
            physics_weight=physics_weight,
            change_weight=change_weight,
            mechanism_weight=mechanism_weight,
            risk_weight=risk_weight,
            include_physics=include_physics,
        )
        score = val_loss if not np.isnan(val_loss) else train_loss
        if score < best_val:
            best_val = score
            best_state = copy.deepcopy(model.state_dict())
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})

    model.load_state_dict(best_state)
    return model, history


def collect_predictions(
    model: torch.nn.Module,
    loader: torch.utils.data.DataLoader,
    split_name: str,
    model_name: str,
    device: torch.device,
) -> tuple[pd.DataFrame, np.ndarray]:
    rows = []
    saliency_batches = []
    model.eval()

    with torch.no_grad():
        for batch in loader:
            batch = move_batch(batch, device)
            outputs = model(batch["x"], batch["x_raw"])
            saliency_batches.append(outputs["causal_saliency"].detach().cpu().numpy())
            actual_turbidity = batch["y_turbidity"].detach().cpu().numpy()
            actual_clearness = batch["y_clearness"].detach().cpu().numpy()
            pred_turbidity = outputs["turbidity_pred"].detach().cpu().numpy()
            pred_clearness = outputs["clearness_pred"].detach().cpu().numpy()

            for index, target_date in enumerate(batch["target_date"]):
                row = {
                    "model": model_name,
                    "split": split_name,
                    "target_date": target_date,
                    "actual_turbidity": float(actual_turbidity[index]),
                    "predicted_turbidity": float(pred_turbidity[index]),
                    "actual_clearness": float(actual_clearness[index]),
                    "predicted_clearness": float(pred_clearness[index]),
                    "actual_turbidity_delta": float(
                        batch["y_turbidity_delta"].detach().cpu().numpy()[index]
                    ),
                    "actual_clearness_delta": float(
                        batch["y_clearness_delta"].detach().cpu().numpy()[index]
                    ),
                    "actual_self_purification_failure": float(
                        batch["y_self_purification_failure"].detach().cpu().numpy()[index]
                    ),
                    "actual_turbidity_surge": float(
                        batch["y_turbidity_surge"].detach().cpu().numpy()[index]
                    ),
                    "actual_critical_transition": float(
                        batch["y_critical_transition"].detach().cpu().numpy()[index]
                    ),
                    "predicted_self_purification_failure_prob": float(
                        outputs["self_purification_failure_prob"].detach().cpu().numpy()[index]
                    ),
                    "predicted_turbidity_surge_prob": float(
                        outputs["turbidity_surge_prob"].detach().cpu().numpy()[index]
                    ),
                    "predicted_critical_transition_prob": float(
                        outputs["critical_transition_prob"].detach().cpu().numpy()[index]
                    ),
                }
                if "physics_turbidity_pred" in outputs:
                    row["physics_turbidity"] = float(
                        outputs["physics_turbidity_pred"].detach().cpu().numpy()[index]
                    )
                    row["physics_clearness"] = float(
                        outputs["physics_clearness_pred"].detach().cpu().numpy()[index]
                    )
                    row["fusion_ratio"] = float(
                        outputs["fusion_ratio"].detach().cpu().numpy()[index]
                    )
                for optional_key in [
                    "velocity_proxy",
                    "bed_shear_proxy",
                    "erosion_source",
                    "runoff_source",
                    "tidal_source",
                    "phytoplankton_source",
                    "krone_deposition_sink",
                    "flushing_sink",
                    "purification_sink",
                    "source_total",
                    "sink_total",
                    "physics_delta_log_turbidity",
                ]:
                    if optional_key in outputs:
                        row[optional_key] = float(
                            outputs[optional_key].detach().cpu().numpy()[index]
                        )
                rows.append(row)

    saliency = np.concatenate(saliency_batches, axis=0) if saliency_batches else np.zeros((0, 0))
    return pd.DataFrame(rows), saliency


def evaluate_model(predictions: pd.DataFrame) -> dict[str, dict[str, float]]:
    metrics = {}
    for split_name, split_df in predictions.groupby("split"):
        split_metrics: dict[str, Any] = {
            "turbidity": regression_metrics(
                split_df["actual_turbidity"], split_df["predicted_turbidity"]
            ),
            "clearness": regression_metrics(
                split_df["actual_clearness"], split_df["predicted_clearness"]
            ),
        }
        if {
            "actual_self_purification_failure",
            "predicted_self_purification_failure_prob",
        }.issubset(split_df.columns):
            split_metrics["self_purification_failure"] = {
                "event_rate": float(split_df["actual_self_purification_failure"].mean()),
                "mean_predicted_probability": float(
                    split_df["predicted_self_purification_failure_prob"].mean()
                ),
            }
        if {"actual_turbidity_surge", "predicted_turbidity_surge_prob"}.issubset(split_df.columns):
            split_metrics["turbidity_surge"] = {
                "event_rate": float(split_df["actual_turbidity_surge"].mean()),
                "mean_predicted_probability": float(
                    split_df["predicted_turbidity_surge_prob"].mean()
                ),
            }
        if {
            "actual_critical_transition",
            "predicted_critical_transition_prob",
        }.issubset(split_df.columns):
            split_metrics["critical_transition"] = {
                "event_rate": float(split_df["actual_critical_transition"].mean()),
                "mean_predicted_probability": float(
                    split_df["predicted_critical_transition_prob"].mean()
                ),
            }
        metrics[split_name] = split_metrics
    return metrics


def dataset_to_numpy(dataset: Any) -> tuple[np.ndarray, ...]:
    x_rows = []
    y_turbidity = []
    y_clearness = []
    dates = []
    last_turbidity = []
    last_clearness = []

    for sample in dataset.samples:
        x_rows.append(np.asarray(sample["x_raw"], dtype=np.float32).reshape(-1))
        y_turbidity.append(float(sample["y_turbidity"]))
        y_clearness.append(float(sample["y_clearness"]))
        dates.append(sample["target_date"])
        last_turbidity.append(float(sample["last_turbidity"]))
        last_clearness.append(float(sample["last_clearness"]))

    return (
        np.asarray(x_rows, dtype=np.float32),
        np.asarray(y_turbidity, dtype=np.float32),
        np.asarray(y_clearness, dtype=np.float32),
        np.asarray(dates),
        np.asarray(last_turbidity, dtype=np.float32),
        np.asarray(last_clearness, dtype=np.float32),
    )


def build_predictions_frame(
    model_name: str,
    split_name: str,
    dates: np.ndarray,
    actual_turbidity: np.ndarray,
    predicted_turbidity: np.ndarray,
    actual_clearness: np.ndarray,
    predicted_clearness: np.ndarray,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": model_name,
            "split": split_name,
            "target_date": dates,
            "actual_turbidity": actual_turbidity.astype(float),
            "predicted_turbidity": predicted_turbidity.astype(float),
            "actual_clearness": actual_clearness.astype(float),
            "predicted_clearness": predicted_clearness.astype(float),
        }
    )


def build_persistence_baseline(prepared: PreparedData) -> pd.DataFrame:
    frames = []
    for split_name, loader in [
        ("train", prepared.train_loader),
        ("val", prepared.val_loader),
        ("test", prepared.test_loader),
    ]:
        _, y_turbidity, y_clearness, dates, last_turbidity, last_clearness = dataset_to_numpy(
            loader.dataset
        )
        frames.append(
            build_predictions_frame(
                model_name="persistence_baseline",
                split_name=split_name,
                dates=dates,
                actual_turbidity=y_turbidity,
                predicted_turbidity=last_turbidity,
                actual_clearness=y_clearness,
                predicted_clearness=last_clearness,
            )
        )
    return pd.concat(frames, ignore_index=True)


def build_ridge_baseline(prepared: PreparedData) -> pd.DataFrame:
    train_x, train_y_turbidity, train_y_clearness, train_dates, _, _ = dataset_to_numpy(
        prepared.train_loader.dataset
    )
    val_x, val_y_turbidity, val_y_clearness, val_dates, _, _ = dataset_to_numpy(
        prepared.val_loader.dataset
    )
    test_x, test_y_turbidity, test_y_clearness, test_dates, _, _ = dataset_to_numpy(
        prepared.test_loader.dataset
    )

    ridge = Ridge(alpha=1.0, random_state=42)
    ridge.fit(train_x, np.column_stack([train_y_turbidity, train_y_clearness]))
    frames = []
    for split_name, x_values, y_turbidity, y_clearness, dates in [
        ("train", train_x, train_y_turbidity, train_y_clearness, train_dates),
        ("val", val_x, val_y_turbidity, val_y_clearness, val_dates),
        ("test", test_x, test_y_turbidity, test_y_clearness, test_dates),
    ]:
        predictions = ridge.predict(x_values)
        frames.append(
            build_predictions_frame(
                model_name="ridge_window_baseline",
                split_name=split_name,
                dates=dates,
                actual_turbidity=y_turbidity,
                predicted_turbidity=np.clip(predictions[:, 0], a_min=0.0, a_max=None),
                actual_clearness=y_clearness,
                predicted_clearness=np.clip(predictions[:, 1], a_min=0.0, a_max=1.0),
            )
        )
    return pd.concat(frames, ignore_index=True)


def save_training_history(
    history_by_model: dict[str, list[dict[str, float]]], output_dir: Path
) -> None:
    history_dir = ensure_dir(output_dir / "training")
    save_json(history_by_model, history_dir / "training_history.json")

    for model_name, history in history_by_model.items():
        if not history:
            continue
        history_df = pd.DataFrame(history)
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(history_df["epoch"], history_df["train_loss"], label="train")
        ax.plot(history_df["epoch"], history_df["val_loss"], label="val")
        ax.set_title(f"{model_name} loss")
        ax.set_xlabel("epoch")
        ax.set_ylabel("loss")
        ax.legend()
        fig.tight_layout()
        fig.savefig(history_dir / f"{model_name}_loss.png", dpi=180)
        plt.close(fig)


def save_model_checkpoints(
    models: dict[str, torch.nn.Module],
    prepared: PreparedData,
    output_dir: Path,
    config: dict[str, Any],
    dataset_summary: dict[str, Any],
) -> None:
    model_dir = ensure_dir(output_dir / "models")
    checkpoint_meta = {
        "feature_columns": prepared.feature_columns,
        "feature_index": prepared.feature_index,
        "history_days": int(config["history_days"]),
        "horizon_days": int(config["horizon_days"]),
        "train_ratio": float(config["train_ratio"]),
        "val_ratio": float(config["val_ratio"]),
        "clearness_transform": dataset_summary.get("clearness_transform"),
    }
    for model_name, model in models.items():
        checkpoint = {
            "model_name": model_name,
            "state_dict": model.state_dict(),
            "meta": checkpoint_meta,
        }
        torch.save(checkpoint, model_dir / f"{model_name}.pt")


def save_prediction_plots(predictions: pd.DataFrame, output_dir: Path) -> None:
    plot_dir = ensure_dir(output_dir / "plots")
    test_df = predictions[predictions["split"] == "test"].copy()
    if test_df.empty:
        return
    test_df["target_date"] = pd.to_datetime(test_df["target_date"])
    test_df = test_df.sort_values("target_date")

    for metric_name, actual_column, predicted_column in [
        ("turbidity", "actual_turbidity", "predicted_turbidity"),
        ("clearness", "actual_clearness", "predicted_clearness"),
    ]:
        fig, ax = plt.subplots(figsize=(11, 4.5))
        for model_name, model_df in test_df.groupby("model"):
            ax.plot(
                model_df["target_date"],
                model_df[predicted_column],
                label=model_name,
                linewidth=1.4,
            )
        first_model_df = next(iter(test_df.groupby("model")))[1]
        ax.plot(
            first_model_df["target_date"],
            first_model_df[actual_column],
            label=f"actual_{metric_name}",
            linewidth=1.3,
            color="black",
        )
        ax.set_title(f"Test {metric_name} comparison")
        ax.set_xlabel("date")
        ax.set_ylabel(metric_name)
        locator = mdates.AutoDateLocator(minticks=5, maxticks=9)
        formatter = mdates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(ncols=3)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(plot_dir / f"test_{metric_name}.png", dpi=180)
        plt.close(fig)


def save_model_comparison(metrics: dict[str, Any], output_dir: Path) -> pd.DataFrame:
    rows = []
    for model_name, model_metrics in metrics.items():
        if model_name == "data":
            continue
        for split_name, split_metrics in model_metrics.items():
            rows.append(
                {
                    "model": model_name,
                    "split": split_name,
                    "turbidity_mae": split_metrics["turbidity"]["mae"],
                    "turbidity_rmse": split_metrics["turbidity"]["rmse"],
                    "turbidity_r2": split_metrics["turbidity"]["r2"],
                    "clearness_mae": split_metrics["clearness"]["mae"],
                    "clearness_rmse": split_metrics["clearness"]["rmse"],
                    "clearness_r2": split_metrics["clearness"]["r2"],
                }
            )
    comparison_df = pd.DataFrame(rows).sort_values(
        ["split", "turbidity_r2"], ascending=[True, False]
    )
    comparison_df.to_csv(
        output_dir / "metrics" / "model_comparison.csv", index=False, encoding="utf-8-sig"
    )
    return comparison_df


def build_feature_importance(
    feature_columns: list[str],
    saliency_by_model: dict[str, np.ndarray],
    output_path: Path,
) -> pd.DataFrame:
    rows = []
    for model_name, saliency in saliency_by_model.items():
        if saliency.size == 0:
            continue
        mean_saliency = saliency.mean(axis=0)
        for feature_name, score in zip(feature_columns, mean_saliency):
            rows.append(
                {
                    "model": model_name,
                    "feature": feature_name,
                    "importance": float(score),
                }
            )

    feature_importance = pd.DataFrame(rows)
    if feature_importance.empty:
        feature_importance = pd.DataFrame(columns=["model", "feature", "importance"])
    else:
        feature_importance = feature_importance.sort_values(
            ["model", "importance"], ascending=[True, False]
        )
    ensure_dir(output_path.parent)
    feature_importance.to_csv(output_path, index=False, encoding="utf-8-sig")
    return feature_importance


def build_knowledge_enhancement_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if "mscim" in metrics and "mscim_no_kg" in metrics:
        summary["kg_ablation_test_delta"] = {
            "turbidity_r2_gain": float(
                metrics["mscim"]["test"]["turbidity"]["r2"]
                - metrics["mscim_no_kg"]["test"]["turbidity"]["r2"]
            ),
            "clearness_r2_gain": float(
                metrics["mscim"]["test"]["clearness"]["r2"]
                - metrics["mscim_no_kg"]["test"]["clearness"]["r2"]
            ),
            "turbidity_rmse_change": float(
                metrics["mscim"]["test"]["turbidity"]["rmse"]
                - metrics["mscim_no_kg"]["test"]["turbidity"]["rmse"]
            ),
            "clearness_rmse_change": float(
                metrics["mscim"]["test"]["clearness"]["rmse"]
                - metrics["mscim_no_kg"]["test"]["clearness"]["rmse"]
            ),
        }
    if "mscim" in metrics and "ridge_window_baseline" in metrics:
        summary["vs_ridge_test_delta"] = {
            "turbidity_r2_gain": float(
                metrics["mscim"]["test"]["turbidity"]["r2"]
                - metrics["ridge_window_baseline"]["test"]["turbidity"]["r2"]
            ),
            "clearness_r2_gain": float(
                metrics["mscim"]["test"]["clearness"]["r2"]
                - metrics["ridge_window_baseline"]["test"]["clearness"]["r2"]
            ),
        }
    if "mscim" in metrics and "persistence_baseline" in metrics:
        summary["vs_persistence_test_delta"] = {
            "turbidity_r2_gain": float(
                metrics["mscim"]["test"]["turbidity"]["r2"]
                - metrics["persistence_baseline"]["test"]["turbidity"]["r2"]
            ),
            "clearness_r2_gain": float(
                metrics["mscim"]["test"]["clearness"]["r2"]
                - metrics["persistence_baseline"]["test"]["clearness"]["r2"]
            ),
        }
    return summary


def write_run_summary(
    output_dir: Path,
    dataset_summary: dict[str, Any],
    split_summary: dict[str, Any],
    metrics: dict[str, Any],
    feature_importance: pd.DataFrame,
) -> None:
    top_rows = []
    for model_name in feature_importance["model"].drop_duplicates().tolist():
        model_df = feature_importance[feature_importance["model"] == model_name].head(5)
        top_rows.append(
            f"- {model_name}: "
            + ", ".join(
                f"{row.feature} ({row.importance:.3f})" for row in model_df.itertuples(index=False)
            )
        )

    test_metrics = {
        model_name: {
            "turbidity_r2": round(float(model_metrics["test"]["turbidity"]["r2"]), 4),
            "clearness_r2": round(float(model_metrics["test"]["clearness"]["r2"]), 4),
            "turbidity_rmse": round(float(model_metrics["test"]["turbidity"]["rmse"]), 4),
            "clearness_rmse": round(float(model_metrics["test"]["clearness"]["rmse"]), 4),
        }
        for model_name, model_metrics in metrics.items()
        if model_name != "data" and "test" in model_metrics
    }

    content = f"""# WaterExpert Pipeline Run Summary

## 1. Completed Outputs

- Built the Wusongkou daily multimodal dataset for MSCIM and CMFBE-ST-GCN prototype training.
- Converted the lightweight GraphRAG relationship table into feature-graph priors.
- Trained `MSCIM`, `MSCIM-NoKG`, `CMFBE-ST-GCN`, and window baselines with auxiliary critical-transition risk outputs.
- Exported predictions, metrics, feature importance, turbidity-driver diagnosis, physics notes, plots, and checkpoints.

## 2. Data Scope

- Water-quality station: Wusongkou / station 2586
- Daily merged rows: {dataset_summary["rows_after_merge"]}
- Date range: {dataset_summary["date_range"]["start"]} to {dataset_summary["date_range"]["end"]}
- Selected weather station: Baoshan
- Hydrodynamic references: Songpu Bridge and Huangdu
- Trainable feature count: {len(dataset_summary["feature_columns"])}

## 3. Data Splits

- Train: {split_summary["train_rows"]} rows, {split_summary["train_windows"]} windows
- Validation: {split_summary["val_rows"]} rows, {split_summary["val_windows"]} windows
- Test: {split_summary["test_rows"]} rows, {split_summary["test_windows"]} windows

## 4. Metrics Snapshot

```json
{json.dumps(test_metrics, ensure_ascii=True, indent=2)}
```

## 5. Main Driver Features

{chr(10).join(top_rows)}

## 6. Current Boundaries

- The boundary-detection head is reserved but not supervised by raster or UAV labels yet.
- The current graph is a single-station feature graph, not a multi-section river-network graph.
- The physics component is a runnable source-sink surrogate, not a calibrated 2D hydrodynamic solver.
- The self-purification failure and critical-transition outputs are empirical prototype risks, not physically calibrated failure probabilities.
"""
    (output_dir / "run_summary.md").write_text(content, encoding="utf-8")


def export_agent_threshold_knowledge(
    predictions: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    threshold_context: pd.DataFrame,
    output_dir: Path,
) -> None:
    knowledge_dir = ensure_dir(output_dir / "thresholds")
    latest_test = predictions[
        (predictions["model"] == "cmfbe_stgcn") & (predictions["split"] == "test")
    ].copy()
    latest_test["target_date"] = pd.to_datetime(latest_test["target_date"])

    top_thresholds = threshold_summary[threshold_summary["status"] == "ok"].copy()
    top_thresholds = top_thresholds.sort_values(
        ["r2_gain", "piecewise_r2"], ascending=False
    ).head(12)
    context_thresholds = threshold_context[threshold_context["status"] == "ok"].copy()
    context_thresholds = context_thresholds.sort_values(
        ["r2_gain", "piecewise_r2"], ascending=False
    ).head(24)

    knowledge_graph = {
        "graph_name": "mechanism_parameter_threshold_knowledge_graph",
        "scope": "wusongkou_daily_prototype",
        "threshold_semantics": (
            "Thresholds denote empirical critical levels at which turbidity forcing tends to exceed "
            "self-purification capacity or turbidity tends to increase sharply in the current prototype."
        ),
        "risk_snapshot": {},
        "threshold_nodes": [],
        "contextual_threshold_nodes": [],
        "guardrails": [
            "Do not reinterpret these thresholds as calibrated 2D hydrodynamic physical thresholds.",
            "Use them for screening, triage, and agent reasoning within the Wusongkou daily prototype.",
            "Escalate to multi-station or physically calibrated workflows when spatial or control claims are requested.",
        ],
    }
    if not latest_test.empty:
        knowledge_graph["risk_snapshot"] = {
            "test_window_start": str(latest_test["target_date"].min().date()),
            "test_window_end": str(latest_test["target_date"].max().date()),
            "critical_transition_rate": float(latest_test["actual_critical_transition"].mean()),
            "mean_predicted_critical_transition_probability": float(
                latest_test["predicted_critical_transition_prob"].mean()
            ),
            "self_purification_failure_rate": float(
                latest_test["actual_self_purification_failure"].mean()
            ),
            "mean_predicted_self_purification_failure_probability": float(
                latest_test["predicted_self_purification_failure_prob"].mean()
            ),
            "turbidity_surge_rate": float(latest_test["actual_turbidity_surge"].mean()),
            "mean_predicted_turbidity_surge_probability": float(
                latest_test["predicted_turbidity_surge_prob"].mean()
            ),
        }

    for row in top_thresholds.itertuples(index=False):
        knowledge_graph["threshold_nodes"].append(
            {
                "node_id": f"threshold::{row.feature}",
                "type": "threshold",
                "feature": row.feature,
                "label": row.feature_label,
                "threshold": float(row.threshold),
                "unit": row.unit,
                "response": row.response,
                "r2_gain": float(row.r2_gain),
                "piecewise_r2": float(row.piecewise_r2),
                "response_jump": float(row.response_jump),
                "interpretation": (
                    "Higher-than-threshold values are associated with stronger net turbidity forcing "
                    "or weaker self-purification in the current Wusongkou prototype."
                ),
            }
        )

    for row in context_thresholds.itertuples(index=False):
        knowledge_graph["contextual_threshold_nodes"].append(
            {
                "node_id": f"context_threshold::{row.context_type}::{row.context}::{row.feature}",
                "type": "contextual_threshold",
                "context_type": row.context_type,
                "context": row.context,
                "feature": row.feature,
                "label": row.feature_label,
                "threshold": float(row.threshold),
                "unit": row.unit,
                "r2_gain": float(row.r2_gain),
                "piecewise_r2": float(row.piecewise_r2),
                "response_jump": float(row.response_jump),
            }
        )

    save_json(knowledge_graph, knowledge_dir / "mechanism_parameter_threshold_kg.json")


def main() -> None:
    args = parse_args()
    config = load_yaml(args.config)

    set_seed(int(config["random_seed"]))
    device = choose_device(config.get("device", "auto"))
    output_dir = ensure_dir(config["output_dir"])
    ensure_dir(output_dir / "metrics")
    ensure_dir(output_dir / "predictions")
    ensure_dir(output_dir / "interpretability")
    ensure_dir(output_dir / "physics")

    hydrodynamics_config = config.get("hydrodynamics", {})
    ndti_config = config.get("ndti", {})
    causal_config = config.get("causal_discovery", {})
    auxiliary_target_config = config.get("auxiliary_targets", {})

    dataset_df, dataset_summary = build_multimodal_dataset(
        data_root=config["data_root"],
        water_pattern=config["water_pattern"],
        weather_filename=config["weather_filename"],
        output_dir=output_dir,
        hydrodynamics_enabled=bool(hydrodynamics_config.get("enabled", False)),
        hydrodynamics_source_path=hydrodynamics_config.get("source_path"),
        hydrodynamics_wide_path=hydrodynamics_config.get("wide_path"),
        hydrodynamics_output_dir=hydrodynamics_config.get("output_dir"),
        ndti_enabled=bool(ndti_config.get("enabled", False)),
        ndti_dir=ndti_config.get("source_dir"),
        ndti_output_dir=ndti_config.get("output_dir"),
    )
    prepared = prepare_dataloaders(
        df=dataset_df,
        feature_columns=dataset_summary["feature_columns"],
        history_days=int(config["history_days"]),
        horizon_days=int(config["horizon_days"]),
        train_ratio=float(config["train_ratio"]),
        val_ratio=float(config["val_ratio"]),
        batch_size=int(config["batch_size"]),
        auxiliary_target_config=auxiliary_target_config,
    )
    sorted_dataset_df = dataset_df.sort_values("date").reset_index(drop=True)
    train_rows = int(prepared.split_summary["train_rows"])
    train_df_for_causality = sorted_dataset_df.iloc[:train_rows].copy()
    adjacency, graph_summary = build_feature_graph_priors(
        rag_artifacts_dir=config["rag_artifacts_dir"],
        feature_columns=dataset_summary["feature_columns"],
        output_dir=output_dir,
        causal_df=train_df_for_causality if bool(causal_config.get("enabled", True)) else None,
        pcmci_tau_max=int(causal_config.get("tau_max", 3)),
        pcmci_pc_alpha=float(causal_config.get("pc_alpha", 0.2)),
        pcmci_alpha_level=float(causal_config.get("alpha_level", 0.05)),
    )

    model_kwargs = {
        "num_features": len(prepared.feature_columns),
        "adjacency": adjacency,
        "feature_index": prepared.feature_index,
        "clearness_log_min": float(dataset_summary["clearness_transform"]["log_turbidity_min"]),
        "clearness_log_max": float(dataset_summary["clearness_transform"]["log_turbidity_max"]),
        "hidden_dim": int(config["model"]["hidden_dim"]),
        "transformer_layers": int(config["model"]["transformer_layers"]),
        "num_heads": int(config["model"]["num_heads"]),
        "dropout": float(config["model"]["dropout"]),
    }
    no_kg_kwargs = {
        **model_kwargs,
        "adjacency": np.eye(len(prepared.feature_columns), dtype=np.float32),
    }

    mscim_model = MSCIMPrototype(**model_kwargs).to(device)
    mscim_no_kg_model = MSCIMPrototype(**no_kg_kwargs).to(device)
    cmfbe_model = CMFBE_STGCNPrototype(**model_kwargs).to(device)

    clearness_weight = float(config["loss"]["clearness_weight"])
    physics_weight = float(config["loss"]["physics_weight"])
    change_weight = float(config["loss"].get("change_weight", 0.25))
    mechanism_weight = float(config["loss"].get("mechanism_weight", 0.18))
    risk_weight = float(config["loss"].get("risk_weight", 0.15))
    epochs = int(config["epochs"])
    learning_rate = float(config["learning_rate"])
    weight_decay = float(config["weight_decay"])

    mscim_model, mscim_history = train_model(
        model=mscim_model,
        prepared=prepared,
        device=device,
        epochs=epochs,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        clearness_weight=clearness_weight,
        physics_weight=physics_weight,
        change_weight=change_weight,
        mechanism_weight=mechanism_weight,
        risk_weight=risk_weight,
        include_physics=False,
    )
    mscim_no_kg_model, mscim_no_kg_history = train_model(
        model=mscim_no_kg_model,
        prepared=prepared,
        device=device,
        epochs=epochs,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        clearness_weight=clearness_weight,
        physics_weight=physics_weight,
        change_weight=change_weight,
        mechanism_weight=mechanism_weight,
        risk_weight=risk_weight,
        include_physics=False,
    )
    cmfbe_model, cmfbe_history = train_model(
        model=cmfbe_model,
        prepared=prepared,
        device=device,
        epochs=epochs,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        clearness_weight=clearness_weight,
        physics_weight=physics_weight,
        change_weight=change_weight,
        mechanism_weight=mechanism_weight,
        risk_weight=risk_weight,
        include_physics=True,
    )

    history_by_model = {
        "mscim": mscim_history,
        "mscim_no_kg": mscim_no_kg_history,
        "cmfbe_stgcn": cmfbe_history,
    }
    save_training_history(history_by_model, output_dir)
    save_model_checkpoints(
        models={
            "mscim": mscim_model,
            "mscim_no_kg": mscim_no_kg_model,
            "cmfbe_stgcn": cmfbe_model,
        },
        prepared=prepared,
        output_dir=output_dir,
        config=config,
        dataset_summary=dataset_summary,
    )

    all_predictions = []
    saliency_by_model: dict[str, np.ndarray] = {}
    metrics = {
        "data": {
            "dataset_summary": dataset_summary,
            "graph_summary": graph_summary,
            "split_summary": prepared.split_summary,
        }
    }

    for model_name, model in [
        ("mscim", mscim_model),
        ("mscim_no_kg", mscim_no_kg_model),
        ("cmfbe_stgcn", cmfbe_model),
    ]:
        model_predictions = []
        saliency_parts = []
        for split_name, loader in [
            ("train", prepared.train_loader),
            ("val", prepared.val_loader),
            ("test", prepared.test_loader),
        ]:
            split_predictions, split_saliency = collect_predictions(
                model=model,
                loader=loader,
                split_name=split_name,
                model_name=model_name,
                device=device,
            )
            model_predictions.append(split_predictions)
            if split_saliency.size:
                saliency_parts.append(split_saliency)
        prediction_df = pd.concat(model_predictions, ignore_index=True)
        all_predictions.append(prediction_df)
        saliency_by_model[model_name] = (
            np.concatenate(saliency_parts, axis=0) if saliency_parts else np.zeros((0, 0))
        )
        metrics[model_name] = evaluate_model(prediction_df)

    ridge_predictions = build_ridge_baseline(prepared)
    persistence_predictions = build_persistence_baseline(prepared)
    all_predictions.extend([ridge_predictions, persistence_predictions])
    metrics["ridge_window_baseline"] = evaluate_model(ridge_predictions)
    metrics["persistence_baseline"] = evaluate_model(persistence_predictions)

    all_predictions_df = pd.concat(all_predictions, ignore_index=True)
    all_predictions_df.to_csv(
        output_dir / "predictions" / "predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )

    feature_importance = build_feature_importance(
        feature_columns=prepared.feature_columns,
        saliency_by_model=saliency_by_model,
        output_path=output_dir / "interpretability" / "feature_importance.csv",
    )
    diagnosis_outputs = diagnose_mscim_turbidity(
        model=mscim_model,
        loader=prepared.test_loader,
        feature_columns=prepared.feature_columns,
        feature_to_domains=graph_summary["feature_to_domains"],
        device=device,
        output_dir=output_dir,
        top_k=3,
    )

    model_comparison = save_model_comparison(metrics, output_dir)
    knowledge_summary = build_knowledge_enhancement_summary(metrics)
    save_json(knowledge_summary, output_dir / "metrics" / "knowledge_enhancement_summary.json")

    physics_coefficients = cmfbe_model.get_physics_coefficients()
    save_json(physics_coefficients, output_dir / "physics" / "physics_coefficients.json")
    export_physics_note(
        output_dir / "physics" / "physics_equations.md",
        coefficients=physics_coefficients,
        data_summary=dataset_summary,
    )

    save_json(metrics, output_dir / "metrics" / "metrics.json")
    save_prediction_plots(all_predictions_df, output_dir)
    write_run_summary(
        output_dir=output_dir,
        dataset_summary=dataset_summary,
        split_summary=prepared.split_summary,
        metrics=metrics,
        feature_importance=feature_importance,
    )
    threshold_summary_path = output_dir / "thresholds" / "cmfbe_threshold_summary.csv"
    threshold_context_path = output_dir / "thresholds" / "cmfbe_thresholds_by_context.csv"
    if threshold_summary_path.exists() and threshold_context_path.exists():
        export_agent_threshold_knowledge(
            predictions=all_predictions_df,
            threshold_summary=pd.read_csv(threshold_summary_path),
            threshold_context=pd.read_csv(threshold_context_path),
            output_dir=output_dir,
        )

    summary_note = {
        "best_test_turbidity_model": model_comparison[
            model_comparison["split"] == "test"
        ].sort_values("turbidity_r2", ascending=False).iloc[0]["model"],
        "best_test_clearness_model": model_comparison[
            model_comparison["split"] == "test"
        ].sort_values("clearness_r2", ascending=False).iloc[0]["model"],
        "mscim_diagnosis_outputs": {key: str(value) for key, value in diagnosis_outputs.items()},
    }
    save_json(summary_note, output_dir / "metrics" / "best_model_summary.json")

    print(f"Pipeline completed. Outputs saved to: {output_dir}")


if __name__ == "__main__":
    main()
