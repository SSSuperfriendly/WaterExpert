from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WaterState:
    timestep: int
    features: dict[str, Any]


@dataclass
class DiagnosisResult:
    source: str
    outputs: dict[str, Any]


@dataclass
class ActionResult:
    action: dict[str, Any]
    safe_action: dict[str, Any]
    metrics: dict[str, float]
