"""
Safe-SAC trainer for RL-TGRR water quality control policy.

Trains a constrained reinforcement learning policy to learn optimal
control actions (release rate, aeration intensity, chemical dosage)
for water turbidity reduction.

Policy is saved to outputs/policy/checkpoints/ and can be loaded by RLTGRRAgent.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3.sac import SAC
from stable_baselines3.common.callbacks import CheckpointCallback


class WaterQualityControlEnv(gym.Env):
    """
    Gymnasium environment for water quality control.
    
    State: [turbidity, water_temp, dissolved_oxygen, precipitation_3d, rainfall_7d, chlorophyll]
    Action: [release_rate, aeration_intensity, chemical_dosage]
    Goal: Minimize turbidity while controlling cost and maintaining stability
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        data_loader: Any | None = None,
        horizon: int = 30,
        start_idx: int = 0,
    ) -> None:
        """
        Initialize environment.

        Args:
            data_loader: WaterQualityDataLoader instance
            horizon: Episode length (days)
            start_idx: Starting index in dataset
        """
        super().__init__()
        self.data_loader = data_loader
        self.horizon = horizon
        self.start_idx = start_idx
        self.current_step = 0
        self.episode_data = []

        # State space: 6 features normalized to [0, 1]
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(6,), dtype=np.float32
        )

        # Action space: 3 continuous actions
        # release_rate: [0, 15] m³/s
        # aeration_intensity: [0, 100] kW
        # chemical_dosage: [0, 500] kg/day
        self.action_space = spaces.Box(
            low=np.array([0.0, 0.0, 0.0]),
            high=np.array([15.0, 100.0, 500.0]),
            dtype=np.float32,
        )

        # Normalization constants
        self.turbidity_norm = 10.0  # NTU
        self.temp_norm = 30.0  # °C
        self.oxygen_norm = 12.0  # mg/L
        self.rainfall_norm = 100.0  # mm
        self.chlorophyll_norm = 20.0  # μg/L
        self.effect_weights = {
            "flow": 0.18,
            "aeration": 0.09,
            "chemical": 0.09,
        }

    def reset(self, seed: int | None = None, options: dict | None = None):
        """Reset environment to random state from dataset."""
        super().reset(seed=seed)

        if self.data_loader is not None:
            # Sample random window from dataset
            max_start = max(0, self.data_loader.get_total_rows() - self.horizon - 1)
            episode_start = self.np_random.integers(0, max_start) if max_start > 0 else 0
            self.episode_data = self.data_loader.iterate_date_range(
                start_date=self.data_loader.merged_df.iloc[episode_start]["date"].strftime("%Y-%m-%d"),
                end_date=self.data_loader.merged_df.iloc[episode_start + self.horizon - 1]["date"].strftime("%Y-%m-%d"),
            )
        else:
            # Dummy data for testing
            self.episode_data = [self._dummy_state() for _ in range(self.horizon)]

        self.current_step = 0
        obs = self._get_observation(self.episode_data[0])

        return obs, {}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        """
        Execute action and return step results.

        Args:
            action: [release_rate, aeration_intensity, chemical_dosage]

        Returns:
            obs, reward, terminated, truncated, info
        """
        if self.current_step >= self.horizon:
            raise RuntimeError("Episode already finished")

        # Get current state
        current_state = self.episode_data[self.current_step]
        current_turbidity = self._finite_value(current_state.get("turbidity", 0.0), 0.0)

        # Simulate effect of action on turbidity
        action = np.nan_to_num(action, nan=0.0, posinf=0.0, neginf=0.0)
        action = np.clip(action, self.action_space.low, self.action_space.high)
        release_rate, aeration_intensity, chemical_dosage = action

        # Simple dynamics model
        turbidity_reduction = (
            self.effect_weights["flow"] * min(release_rate / 10.0, 1.0)
            + self.effect_weights["aeration"] * min(aeration_intensity / 50.0, 1.0)
            + self.effect_weights["chemical"] * min(chemical_dosage / 100.0, 1.0)
        )
        turbidity_reduction = np.clip(turbidity_reduction, 0.0, 0.4)

        # New turbidity (with some stochasticity)
        next_turbidity = max(0.0, current_turbidity * (1.0 - float(turbidity_reduction)))

        # Cost of action
        action_cost = (
            0.02 * release_rate +  # ¥/m³
            0.5 * aeration_intensity +  # ¥/kW
            0.1 * chemical_dosage  # ¥/kg
        )

        # Reward function (multi-objective)
        # Maximize turbidity reduction, minimize cost, encourage stability
        turbidity_reward = (current_turbidity - next_turbidity) * 10.0  # Scale for importance
        cost_penalty = -float(action_cost) * 0.03
        normalized_action = np.array(
            [release_rate / 15.0, aeration_intensity / 100.0, chemical_dosage / 500.0],
            dtype=np.float32,
        )
        stability_bonus = -0.1 * float(np.sum(normalized_action**2))

        reward = turbidity_reward + cost_penalty + stability_bonus

        # Constraint: safety check (soft constraint via reward penalty)
        if release_rate > 15.0 or aeration_intensity > 100.0 or chemical_dosage > 500.0:
            reward -= 10.0  # Large penalty for constraint violation

        # Advance step
        self.current_step += 1
        terminated = self.current_step >= self.horizon
        truncated = False

        # Get next observation
        next_state = self.episode_data[self.current_step] if not terminated else current_state
        obs = self._get_observation(next_state)

        info = {
            "turbidity": float(next_turbidity),
            "cost": float(action_cost),
            "turbidity_reduction": float(current_turbidity - next_turbidity),
        }

        return obs, float(reward), terminated, truncated, info

    def _get_observation(self, state: dict[str, Any]) -> np.ndarray:
        """Normalize state to observation."""
        obs = np.array(
            [
                self._finite_value(state.get("turbidity", 0.0), 0.0) / self.turbidity_norm,
                self._finite_value(state.get("water_temp", 15.0), 15.0) / self.temp_norm,
                self._finite_value(state.get("dissolved_oxygen", 8.0), 8.0) / self.oxygen_norm,
                self._finite_value(state.get("rainfall_3d", 0.0), 0.0) / self.rainfall_norm,
                self._finite_value(state.get("rainfall_7d", 0.0), 0.0) / self.rainfall_norm,
                self._finite_value(state.get("chlorophyll_a", 0.0), 0.0) / self.chlorophyll_norm,
            ],
            dtype=np.float32,
        )
        obs = np.nan_to_num(obs, nan=0.0, posinf=1.0, neginf=0.0)
        return np.clip(obs, 0.0, 1.0)

    def _finite_value(self, value: Any, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return numeric if np.isfinite(numeric) else default

    def _dummy_state(self) -> dict[str, Any]:
        """Generate dummy state for testing."""
        return {
            "turbidity": np.random.uniform(1.0, 5.0),
            "water_temp": 20.0,
            "dissolved_oxygen": 8.0,
            "rainfall_3d": 0.0,
            "rainfall_7d": 0.0,
            "chlorophyll_a": 0.0,
        }

    def render(self) -> None:
        """Not implemented."""
        pass


class RLTGRRTrainer:
    """Train Safe-SAC policy for water quality control."""

    def __init__(
        self,
        data_loader: Any,
        output_dir: str = "outputs/policy",
        config: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize trainer.

        Args:
            data_loader: WaterQualityDataLoader instance
            output_dir: Directory for saving checkpoints
            config: Training configuration
        """
        self.data_loader = data_loader
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir = self.output_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        self.config = config or {}
        self.learning_rate = float(self.config.get("learning_rate", 3e-4))
        self.batch_size = int(self.config.get("batch_size", 256))
        self.buffer_size = int(self.config.get("buffer_size", 100000))
        self.train_timesteps = int(self.config.get("train_timesteps", 50000))
        self.device = self.config.get("device", "auto")

    def train(
        self,
        total_timesteps: int = 50000,
        eval_episodes: int = 10,
        save_freq: int = 5000,
    ) -> dict[str, Any]:
        """
        Train SAC policy.

        Args:
            total_timesteps: Total number of training timesteps
            eval_episodes: Number of episodes for evaluation
            save_freq: Save checkpoint every N timesteps

        Returns:
            Training results dictionary
        """
        print("=" * 80)
        print("RL-TGRR Training (Safe-SAC)")
        print("=" * 80)

        # Create environment
        print("\n[1/3] Creating training environment...")
        env = WaterQualityControlEnv(
            data_loader=self.data_loader,
            horizon=30,  # 30-day episodes
        )
        print(f"     ✓ Environment created")
        print(f"       - Observation space: {env.observation_space}")
        print(f"       - Action space: {env.action_space}")

        # Create SAC agent
        print("\n[2/3] Initializing SAC agent...")
        model = SAC(
            "MlpPolicy",
            env,
            learning_rate=self.learning_rate,
            buffer_size=self.buffer_size,
            batch_size=self.batch_size,
            gamma=0.99,
            tau=0.005,
            ent_coef="auto",
            target_update_interval=1,
            train_freq=(1, "step"),
            device=self.device,
            verbose=1,
        )
        print("     ✓ SAC agent initialized")
        print(f"       - Learning rate: {self.learning_rate}")
        print(f"       - Buffer size: {self.buffer_size}")

        # Callbacks
        checkpoint_callback = CheckpointCallback(
            save_freq=save_freq,
            save_path=str(self.checkpoints_dir),
            name_prefix="rl_model",
            save_replay_buffer=True,
        )

        # Train
        print(f"\n[3/3] Training for {total_timesteps} timesteps...")
        print(f"     (This may take 5-15 minutes on CPU)")

        try:
            model.learn(
                total_timesteps=total_timesteps,
                callback=checkpoint_callback,
                progress_bar=True,
            )

            # Save final model
            final_model_path = self.checkpoints_dir / "final_model"
            model.save(str(final_model_path))
            latest_model_path = self.checkpoints_dir / "latest.zip"
            shutil.copyfile(f"{final_model_path}.zip", latest_model_path)
            print(f"\n     ✓ Final model saved: {final_model_path}.zip")
            print(f"     ✓ Latest policy saved: {latest_model_path}")

            return {
                "status": "success",
                "total_timesteps": total_timesteps,
                "model_path": str(final_model_path),
                "latest_policy_path": str(latest_model_path),
                "checkpoints_dir": str(self.checkpoints_dir),
            }

        except Exception as e:
            print(f"\n     ✗ Training failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }


def main() -> None:
    """Main training entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Train RL-TGRR Safe-SAC policy")
    parser.add_argument(
        "--timesteps",
        type=int,
        default=50000,
        help="Total training timesteps",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=3e-4,
        help="Learning rate",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="Batch size",
    )
    parser.add_argument(
        "--save-freq",
        type=int,
        default=5000,
        help="Save checkpoint every N timesteps",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Training device passed to Stable-Baselines3 (auto, cpu, cuda)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs/policy",
        help="Output directory for checkpoints",
    )

    args = parser.parse_args()

    # Load data
    print("Loading data...")
    from water_ai.data.loader import WaterQualityDataLoader

    loader = WaterQualityDataLoader(target_station=2586)

    # Train
    trainer = RLTGRRTrainer(
        data_loader=loader,
        output_dir=args.output_dir,
        config={
            "learning_rate": args.learning_rate,
            "batch_size": args.batch_size,
            "device": args.device,
        },
    )

    result = trainer.train(
        total_timesteps=args.timesteps,
        save_freq=args.save_freq,
    )

    print("\n" + "=" * 80)
    if result["status"] == "success":
        print("✓ Training completed successfully!")
        print(f"  Model saved at: {result['model_path']}")
        print(f"  Latest policy at: {result['latest_policy_path']}")
        print(f"  Checkpoints at: {result['checkpoints_dir']}")
    else:
        print("✗ Training failed!")
        print(f"  Error: {result.get('error', 'Unknown')}")
    print("=" * 80)


if __name__ == "__main__":
    main()
