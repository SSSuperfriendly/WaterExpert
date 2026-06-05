from __future__ import annotations

import json
import os
import random
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, cast

import numpy as np
import torch
import yaml

DEFAULT_TEXT_ENCODING = "utf-8"
DEFAULT_JSON_INDENT = 2


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def atomic_write_text(path: str | Path, content: str, encoding: str = DEFAULT_TEXT_ENCODING) -> Path:
    target_path = Path(path)
    ensure_dir(target_path.parent)
    with NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        dir=target_path.parent,
        prefix=f"{target_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(target_path)
    return target_path


def load_yaml(path: str | Path) -> dict[str, Any]:
    yaml_path = Path(path)
    try:
        raw_payload = yaml.safe_load(yaml_path.read_text(encoding=DEFAULT_TEXT_ENCODING))
    except FileNotFoundError:
        raise
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {yaml_path}: {exc}") from exc

    if raw_payload is None:
        return {}
    if not isinstance(raw_payload, Mapping):
        raise TypeError(
            f"Expected YAML mapping in {yaml_path}, got {type(raw_payload).__name__}."
        )
    return dict(cast(Mapping[str, Any], raw_payload))


def save_json(obj: Any, path: str | Path) -> Path:
    serialized = json.dumps(obj, ensure_ascii=False, indent=DEFAULT_JSON_INDENT)
    return atomic_write_text(path, serialized)


def set_seed(seed: int) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def resolve_single_path(root: str | Path, pattern: str) -> Path:
    root_path = Path(root)
    matches = sorted(root_path.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched pattern {pattern!r} under {root_path}")
    if len(matches) > 1:
        raise RuntimeError(
            f"Expected one match for {pattern!r} under {root_path}, got {len(matches)}: {matches}"
        )
    return matches[0]
