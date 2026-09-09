from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScenarioClassification:
    scenario: str
    confidence: float
    summary: str


@dataclass
class StrategyDraft:
    objectives: list[str]
    constraints: dict[str, Any]
    suggested_actions: list[dict[str, Any]]
