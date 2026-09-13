from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
SCENARIOS_DIR = OUTPUTS_DIR / "scenarios"
PLOTS_DIR = OUTPUTS_DIR / "plots"

SCENARIO_KEYS = {
    "1": "s1_external_input",
    "2": "s2_internal_release",
    "3": "s3_algae_bloom",
    "4": "s4_chronic_combo",
}

SCENARIO_LABELS = {
    "s1_external_input": "S1 External Input",
    "s2_internal_release": "S2 Internal Release",
    "s3_algae_bloom": "S3 Algae Bloom",
    "s4_chronic_combo": "S4 Chronic Combo",
}


def scenario_key(value: str) -> str:
    return SCENARIO_KEYS.get(str(value), str(value))


def scenario_data_path(key: str, scenario_dir: Path = SCENARIOS_DIR) -> Path:
    return scenario_dir / key / "data.json"


def load_scenario_data(key: str, scenario_dir: Path = SCENARIOS_DIR) -> dict[str, Any]:
    path = scenario_data_path(key, scenario_dir)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_many_scenarios(values: list[str], scenario_dir: Path = SCENARIOS_DIR) -> dict[str, dict[str, Any]]:
    loaded = {}
    for value in values:
        key = scenario_key(value)
        data = load_scenario_data(key, scenario_dir)
        if data:
            loaded[key] = data
    return loaded


def metric(data: dict[str, Any], name: str, default: float = 0.0) -> float:
    metrics = data.get("metrics_summary", {})
    if name in metrics:
        return float(metrics.get(name, default) or default)
    episodes = data.get("episodes", [])
    values = [
        float(ep.get("metrics", {}).get(name, default) or default)
        for ep in episodes
        if isinstance(ep, dict)
    ]
    return float(np.mean(values)) if values else default


def first_episode(data: dict[str, Any], index: int = 0) -> dict[str, Any]:
    episodes = data.get("episodes", [])
    if not episodes:
        return {}
    index = max(0, min(index, len(episodes) - 1))
    return episodes[index]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
