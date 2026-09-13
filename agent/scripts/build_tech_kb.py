from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from water_ai.tech_kb.kg_builder import KnowledgeGraphBuilder
from water_ai.tech_kb.tensor_complete import TensorCompletion

DEFAULT_SEED_PATH = Path("data/tech_knowledge_base/tech_quadruples.jsonl")
DEFAULT_OUTPUT_PATH = Path("data/tech_knowledge_base/applicability_tensor.npz")
EFFECT_METRICS = (
    "turbidity_reduction",
    "sediment_flush",
    "do_improvement",
    "nutrient_control",
    "stability",
    "cost_efficiency",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the remediation technology knowledge-base tensor.")
    parser.add_argument("--seed-path", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--rank", type=int, default=4)
    parser.add_argument("--max-iter", type=int, default=50)
    return parser.parse_args()


def stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def text_of(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    if isinstance(value, dict):
        parts = [str(item) for item in value.values() if item not in (None, "")]
        return "|".join(parts) if parts else default
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value if item not in (None, "")]
        return "|".join(parts) if parts else default
    text = str(value).strip()
    return text if text else default


def first_present(item: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return default


def technology_value(item: dict[str, Any]) -> str:
    return text_of(first_present(item, ("technology", "tech_name", "tech_id")))


def environment_value(item: dict[str, Any]) -> str:
    return text_of(first_present(item, ("environment", "env", "condition")))


def scenario_value(item: dict[str, Any]) -> str:
    return text_of(first_present(item, ("scenario", "scenario_type")))


def collect_axis(triples: list[dict[str, Any]], value_fn) -> list[str]:
    values = [value_fn(item) for item in triples]
    return stable_unique(values) or ["unknown"]


def effect_scores(item: dict[str, Any]) -> np.ndarray:
    effect = item.get("effect", {})
    if isinstance(effect, dict):
        tss = float(effect.get("tss_removal_pct", effect.get("turbidity_reduction_pct", 0.0))) / 100.0
        do_gain = min(float(effect.get("do_increase_mg_l", effect.get("do_improvement_mg_l", 0.0))) / 3.0, 1.0)
        stability = float(effect.get("stability_score", 0.0))
        nutrient = float(effect.get("nutrient_removal_pct", effect.get("nutrient_control_pct", 0.0))) / 100.0
        sediment = float(effect.get("sediment_flush_pct", effect.get("sediment_control_pct", 0.0))) / 100.0
        base = max(tss, nutrient, sediment, do_gain, stability)
    else:
        text = text_of(effect).lower()
        tss = 0.7 if any(token in text for token in ("turbidity", "浊度", "clarity")) else 0.2
        sediment = 0.85 if any(token in text for token in ("sediment", "冲刷", "flush", "底泥")) else 0.15
        do_gain = 0.85 if any(token in text for token in ("do", "oxygen", "曝气", "增氧")) else 0.2
        nutrient = 0.75 if any(token in text for token in ("algae", "藻", "nutrient", "营养")) else 0.2
        stability = 0.6
        base = max(tss, sediment, do_gain, nutrient, stability)

    cost = float(item.get("opex_per_unit", item.get("cost_per_day", 0.0)) or 0.0)
    carbon = float(item.get("carbon_footprint_kg_co2_per_unit", 0.0) or 0.0)
    penalty = min((cost / 2000.0) + (carbon / 50.0), 0.8)
    cost_efficiency = max(base - penalty, 0.0)
    return np.clip(np.array([tss, sediment, do_gain, nutrient, stability, cost_efficiency], dtype=float), 0.0, 1.0)


def build_observed_tensor(triples: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, dict[str, list[str]]]:
    technologies = collect_axis(triples, technology_value)
    environments = collect_axis(triples, environment_value)
    scenarios = collect_axis(triples, scenario_value)
    axes = {
        "technologies": technologies,
        "environments": environments,
        "scenarios": scenarios,
        "effects": list(EFFECT_METRICS),
    }
    shape = (len(technologies), len(environments), len(EFFECT_METRICS), len(scenarios))
    sums = np.zeros(shape, dtype=float)
    counts = np.zeros(shape, dtype=float)
    tech_index = {value: idx for idx, value in enumerate(technologies)}
    env_index = {value: idx for idx, value in enumerate(environments)}
    scenario_index = {value: idx for idx, value in enumerate(scenarios)}

    for item in triples:
        t_idx = tech_index[technology_value(item)]
        e_idx = env_index[environment_value(item)]
        s_idx = scenario_index[scenario_value(item)]
        scores = effect_scores(item)
        sums[t_idx, e_idx, :, s_idx] += scores
        counts[t_idx, e_idx, :, s_idx] += 1.0

    observed = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    mask = counts > 0
    return observed, mask, axes


def save_tensor(
    output_path: Path,
    observed: np.ndarray,
    completed: np.ndarray,
    mask: np.ndarray,
    axes: dict[str, list[str]],
    triples: list[dict[str, Any]],
    rank: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        observed_tensor=observed,
        completed_tensor=completed,
        tensor=completed,
        mask=mask.astype(np.uint8),
        technologies=np.array(axes["technologies"], dtype=str),
        environments=np.array(axes["environments"], dtype=str),
        effects=np.array(axes["effects"], dtype=str),
        scenarios=np.array(axes["scenarios"], dtype=str),
        source_count=np.array(len(triples), dtype=np.int32),
        completion_rank=np.array(rank, dtype=np.int32),
    )
    metadata_path = output_path.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(
            {
                "shape": list(completed.shape),
                "axes": axes,
                "observed_entries": int(mask.sum()),
                "density": float(mask.mean()),
                "source_count": len(triples),
                "completion_rank": rank,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    builder = KnowledgeGraphBuilder(args.seed_path)
    triples = builder.build()
    if not triples:
        raise SystemExit(f"No seed triples found at {args.seed_path}")

    print(f"Loaded {len(triples)} tech triples from {args.seed_path}")
    print("Building applicability tensor...")
    observed, mask, axes = build_observed_tensor(triples)
    print(f"Observed tensor shape: {observed.shape}; density={mask.mean():.3f}")

    trainer = TensorCompletion(args.output, rank=args.rank, max_iter=args.max_iter)
    completed = trainer.complete(mask=mask, observed=observed)
    save_tensor(args.output, observed, completed, mask, axes, triples, args.rank)
    print(f"Applicability tensor saved: {args.output}")


if __name__ == "__main__":
    main()
