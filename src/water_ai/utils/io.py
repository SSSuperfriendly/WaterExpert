from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def save_json(obj: Any, path: str | Path) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as file:
        json.dump(obj, file, ensure_ascii=False, indent=2)
    return path


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_single_path(root: str | Path, pattern: str) -> Path:
    root = Path(root)
    matches = sorted(root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched pattern {pattern!r} under {root}")
    if len(matches) > 1:
        raise RuntimeError(
            f"Expected one match for {pattern!r} under {root}, got {len(matches)}: {matches}"
        )
    return matches[0]
