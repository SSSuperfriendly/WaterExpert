from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .base import BaseAgent

try:
    from stable_baselines3 import SAC
except ImportError:  # pragma: no cover - optional dependency fallback
    SAC = None  # type: ignore[assignment]


class RLTGRRAgent(BaseAgent):
    def __init__(self, name: str = "RLTGRRAgent", config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.policy_path = self.config.get("policy_path", "outputs/policy/checkpoints/latest.zip")
        self.device = self.config.get("device", "auto")
        self.enable_plan_guidance = bool(self.config.get("enable_plan_guidance", True))
        self.plan_guidance_weight = float(self.config.get("plan_guidance_weight", 0.35))
        self.non_recommended_policy_scale = float(self.config.get("non_recommended_policy_scale", 0.6))
        self.policy_status = "not_loaded"
        self.model = self._load_policy()

    def act(self, execution_input: dict[str, Any]) -> dict[str, Any]:
        """Execute low-level control actions via Safe-SAC policy."""
        state = execution_input.get("state", {})
        plan = execution_input.get("plan", {})
        strategy = plan.get("strategy", {})

        action_source = "fallback_rules"
        policy_error = None

        if self.model is not None:
            try:
                action = self._predict_policy_action(state, strategy)
                action_source = "safe_sac_policy_with_plan_guidance" if self.enable_plan_guidance else "safe_sac_policy"
            except Exception as exc:  # keep closed-loop demo resilient
                policy_error = str(exc)
                action = self._fallback_action(strategy)
        else:
            action = self._fallback_action(strategy)

        result = {
            "executor": "RL-TGRR",
            "action": action,
            "policy_path": self.policy_path,
            "policy_status": self.policy_status,
            "action_source": action_source,
        }
        if policy_error:
            result["policy_error"] = policy_error
        return result

    def _load_policy(self) -> Any | None:
        """Load the trained Stable-Baselines3 SAC policy when available."""
        if SAC is None:
            self.policy_status = "stable_baselines3_unavailable"
            return None

        resolved_path = self._resolve_policy_path()
        if resolved_path is None:
            self.policy_status = "missing"
            return None

        try:
            model = SAC.load(str(resolved_path), device=self.device)
        except Exception as exc:
            self.policy_status = f"load_error: {exc}"
            return None

        self.policy_path = str(resolved_path)
        self.policy_status = "loaded"
        return model

    def _resolve_policy_path(self) -> Path | None:
        policy_path = Path(self.policy_path)
        if policy_path.exists():
            return policy_path

        if policy_path.suffix != ".zip":
            zipped_path = policy_path.with_suffix(".zip")
            if zipped_path.exists():
                return zipped_path

        return None

    def _predict_policy_action(self, state: dict[str, Any], strategy: dict[str, Any]) -> dict[str, float]:
        obs = self._state_to_observation(state)
        predicted_action, _ = self.model.predict(obs, deterministic=True)
        action = np.asarray(predicted_action, dtype=np.float32).reshape(-1)
        if action.size < 3:
            action = np.pad(action, (0, 3 - action.size), constant_values=0.0)

        action = np.clip(action[:3], [0.0, 0.0, 0.0], [15.0, 100.0, 500.0])
        if self.enable_plan_guidance:
            action = self._apply_plan_guidance(action, strategy)
        return {
            "release_rate": float(action[0]),
            "aeration_intensity": float(action[1]),
            "chemical_dosage": float(action[2]),
        }

    def _state_to_observation(self, state: dict[str, Any]) -> np.ndarray:
        obs = np.array(
            [
                float(state.get("turbidity", 0.0)) / 10.0,
                float(state.get("water_temp", state.get("temperature", 15.0))) / 30.0,
                float(state.get("dissolved_oxygen", 8.0)) / 12.0,
                float(state.get("rainfall_3d", 0.0)) / 100.0,
                float(state.get("rainfall_7d", 0.0)) / 100.0,
                float(state.get("chlorophyll_a", 0.0)) / 20.0,
            ],
            dtype=np.float32,
        )
        obs = np.nan_to_num(obs, nan=0.0, posinf=1.0, neginf=0.0)
        return np.clip(obs, 0.0, 1.0)

    def _apply_plan_guidance(self, policy_action: np.ndarray, strategy: dict[str, Any]) -> np.ndarray:
        guided_action = np.array(
            [
                policy_action[0] * self.non_recommended_policy_scale,
                policy_action[1] * self.non_recommended_policy_scale,
                policy_action[2] * self.non_recommended_policy_scale,
            ],
            dtype=np.float32,
        )
        fallback_action = self._fallback_action(strategy)
        recommended_dims = self._recommended_action_dimensions(strategy)

        action_order = ["release_rate", "aeration_intensity", "chemical_dosage"]
        guidance_weight = float(np.clip(self.plan_guidance_weight, 0.0, 1.0))
        policy_weight = 1.0 - guidance_weight

        for index, key in enumerate(action_order):
            if key in recommended_dims:
                guided_action[index] = (
                    policy_weight * policy_action[index] + guidance_weight * float(fallback_action.get(key, 0.0))
                )

        guided_action *= self._objective_intensity_scale(strategy)
        return np.clip(guided_action, [0.0, 0.0, 0.0], [15.0, 100.0, 500.0])

    def _recommended_action_dimensions(self, strategy: dict[str, Any]) -> set[str]:
        action_dimensions: set[str] = set()
        for rec_action in strategy.get("recommended_actions", []):
            action_type = rec_action.get("action", "")
            if action_type in {"release_water", "flow_control"}:
                action_dimensions.add("release_rate")
            elif action_type == "aeration":
                action_dimensions.add("aeration_intensity")
            elif action_type == "chemical_dosage":
                action_dimensions.add("chemical_dosage")
        return action_dimensions

    def _objective_intensity_scale(self, strategy: dict[str, Any]) -> float:
        weights = strategy.get("objective_weights", {})
        reduction_weight = float(weights.get("turbidity_reduction", 0.5))
        cost_weight = float(weights.get("cost", 0.2))
        stability_weight = float(weights.get("stability", 0.2))
        scale = 0.85 + 0.20 * reduction_weight - 0.20 * cost_weight - 0.10 * stability_weight
        return float(np.clip(scale, 0.65, 1.0))

    def _fallback_action(self, strategy: dict[str, Any]) -> dict[str, float]:
        recommended_actions = strategy.get("recommended_actions", [])

        action = {
            "release_rate": 0.0,
            "aeration_intensity": 0.0,
            "chemical_dosage": 0.0,
        }

        for rec_action in recommended_actions:
            action_type = rec_action.get("action", "")
            intensity = rec_action.get("intensity", 0.0)

            if action_type == "release_water":
                action["release_rate"] = intensity * 15.0
            elif action_type == "aeration":
                action["aeration_intensity"] = intensity * 60.0
            elif action_type == "chemical_dosage":
                action["chemical_dosage"] = intensity * 100.0
            elif action_type == "flow_control":
                action["release_rate"] = intensity * 8.0

        return action

    def health(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "policy": self.policy_path,
            "policy_status": self.policy_status,
            "status": "ready",
        }
