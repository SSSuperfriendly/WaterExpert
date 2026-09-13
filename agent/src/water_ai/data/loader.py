"""
Real-time data loader for multi-agent water quality management system.

Loads water quality, weather, and hydrodynamic data from CSV files
and provides state dictionaries for agent decision-making.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class WaterQualityDataLoader:
    """Load and process water quality, weather, and hydrodynamic data."""

    def __init__(
        self,
        water_quality_path: str = "data/full_station_database/water_quality_daily_all_stations.csv",
        weather_path: str = "data/raw/shanghai_weather_daily.csv",
        hydrodynamics_path: str = "outputs/hydrodynamics_preprocessed/shanghai_hydrodynamics_daily_wide.csv",
        target_station: int = 2586,
    ) -> None:
        """
        Initialize data loader.

        Args:
            water_quality_path: Path to water quality CSV
            weather_path: Path to weather CSV
            hydrodynamics_path: Path to preprocessed hydrodynamic CSV
            target_station: Target station code (default: Wusongkou 2586)
        """
        self.target_station = target_station
        self.water_quality_path = Path(water_quality_path)
        self.weather_path = Path(weather_path)
        self.hydrodynamics_path = Path(hydrodynamics_path)

        self.water_quality_df = None
        self.weather_df = None
        self.hydrodynamics_df = None
        self.current_index = 0

        self._load_data()

    def _load_data(self) -> None:
        """Load and merge all data sources."""
        print("[DataLoader] Loading water quality data...")
        self.water_quality_df = pd.read_csv(self.water_quality_path)

        # Filter for target station
        self.water_quality_df = self.water_quality_df[
            self.water_quality_df["station_code"] == self.target_station
        ].copy()
        self.water_quality_df["date"] = pd.to_datetime(self.water_quality_df["date"])
        self.water_quality_df = self.water_quality_df.sort_values("date").reset_index(drop=True)

        print(f"[DataLoader] Loaded {len(self.water_quality_df)} water quality records for station {self.target_station}")

        # Load weather data
        print("[DataLoader] Loading weather data...")
        self.weather_df = pd.read_csv(self.weather_path)
        
        # Rename Chinese columns to English
        weather_column_mapping = {
            "气压": "pressure",
            "平均气温": "air_temp",
            "相对湿度": "humidity",
            "当天降水量": "precipitation",
            "平均风速": "wind_speed",
            "平均风向": "wind_dir",
        }
        self.weather_df = self.weather_df.rename(columns=weather_column_mapping)
        
        self.weather_df["date"] = pd.to_datetime(
            self.weather_df[["Year", "Mon", "Day"]].rename(
                columns={"Year": "year", "Mon": "month", "Day": "day"}
            )
        )
        self.weather_df = self.weather_df.sort_values("date").reset_index(drop=True)
        print(f"[DataLoader] Loaded {len(self.weather_df)} weather records")

        # Load hydrodynamics (if available)
        if self.hydrodynamics_path.exists():
            print("[DataLoader] Loading hydrodynamic data...")
            self.hydrodynamics_df = pd.read_csv(self.hydrodynamics_path)
            self.hydrodynamics_df["date"] = pd.to_datetime(self.hydrodynamics_df["date"])
            self.hydrodynamics_df = self.hydrodynamics_df.sort_values("date").reset_index(drop=True)
            print(f"[DataLoader] Loaded {len(self.hydrodynamics_df)} hydrodynamic records")
        else:
            print(f"[DataLoader] Warning: Hydrodynamic file not found at {self.hydrodynamics_path}")
            self.hydrodynamics_df = pd.DataFrame()

        # Merge water quality with weather by date
        self.merged_df = self.water_quality_df.merge(
            self.weather_df[["date", "precipitation", "air_temp", "humidity", "wind_speed"]],
            on="date",
            how="left",
        )

        if not self.hydrodynamics_df.empty:
            self.merged_df = self.merged_df.merge(
                self.hydrodynamics_df,
                on="date",
                how="left",
            )

        self.merged_df = self.merged_df.sort_values("date").reset_index(drop=True)
        print(f"[DataLoader] Merged dataset: {len(self.merged_df)} rows")

        # Calculate rolling features for scenarios
        self._compute_rolling_features()

    def _compute_rolling_features(self) -> None:
        """Compute rolling statistics for scenario detection."""
        # 3-day cumulative precipitation
        self.merged_df["rainfall_3d"] = (
            self.merged_df["precipitation"].fillna(0).rolling(window=3, min_periods=1).sum()
        )

        # 7-day cumulative precipitation
        self.merged_df["rainfall_7d"] = (
            self.merged_df["precipitation"].fillna(0).rolling(window=7, min_periods=1).sum()
        )

        # 7-day baseline turbidity (chronic detection)
        self.merged_df["turbidity_7d_mean"] = (
            self.merged_df["turbidity"].rolling(window=7, min_periods=1).mean()
        )

        # Chlorophyll proxy for algae bloom detection
        self.merged_df["chlorophyll_a"] = self.merged_df.get(
            "chlorophyll_a", pd.Series(0.0, index=self.merged_df.index)
        )

    def reset(self) -> None:
        """Reset to the beginning of the data."""
        self.current_index = 0

    def get_state_at_date(self, date_str: str) -> dict[str, Any] | None:
        """
        Get state dictionary for a specific date.

        Args:
            date_str: Date string in format "YYYY-MM-DD"

        Returns:
            State dictionary or None if date not found
        """
        target_date = pd.to_datetime(date_str)
        matches = self.merged_df[self.merged_df["date"] == target_date]

        if matches.empty:
            return None

        row = matches.iloc[0]
        return self._row_to_state(row)

    def get_state_at_index(self, idx: int) -> dict[str, Any]:
        """
        Get state dictionary at a given index.

        Args:
            idx: Index in the merged dataframe

        Returns:
            State dictionary
        """
        row = self.merged_df.iloc[idx]
        return self._row_to_state(row)

    def get_next_state(self) -> dict[str, Any] | None:
        """
        Get the next state and advance the internal pointer.

        Returns:
            State dictionary or None if end of data reached
        """
        if self.current_index >= len(self.merged_df):
            return None

        row = self.merged_df.iloc[self.current_index]
        self.current_index += 1
        return self._row_to_state(row)

    def _row_to_state(self, row: pd.Series) -> dict[str, Any]:
        """
        Convert a dataframe row to a state dictionary for agents.

        State dictionary includes:
        - Measurements: turbidity, temp, chlorophyll, dissolved_oxygen, etc.
        - Weather: precipitation, air_temp, humidity, wind_speed
        - Computed features: rainfall_3d, rainfall_7d, turbidity_7d_mean
        - Scenario labels: scenario_type
        - Hydrodynamics (if available): flow rates, water levels, etc.
        """
        state = {
            "date": row["date"].strftime("%Y-%m-%d"),
            # Water quality measurements
            "turbidity": float(row.get("turbidity", 0.0)),
            "water_temp": float(row.get("water_temp", 0.0)),
            "dissolved_oxygen": float(row.get("dissolved_oxygen", 0.0)),
            "ph": float(row.get("ph", 0.0)),
            "conductivity": float(row.get("conductivity", 0.0)),
            "chlorophyll_a": float(row.get("chlorophyll_a", 0.0)),
            "algae_density": float(row.get("algae_density", 0.0)),
            "tp": float(row.get("tp", 0.0)),
            "tn": float(row.get("tn", 0.0)),
            "nh3_n": float(row.get("nh3_n", 0.0)),
            # Weather
            "precipitation": float(row.get("precipitation", 0.0)),
            "air_temp": float(row.get("air_temp", 0.0)),
            "humidity": float(row.get("humidity", 0.0)),
            "wind_speed": float(row.get("wind_speed", 0.0)),
            # Rolling features for scenario detection
            "rainfall_3d": float(row.get("rainfall_3d", 0.0)),
            "rainfall_7d": float(row.get("rainfall_7d", 0.0)),
            "turbidity_7d_mean": float(row.get("turbidity_7d_mean", 0.0)),
        }

        # Add hydrodynamic features if available
        hydro_features = [
            "songpu_flow_m3s",
            "huangdu_flow_m3s",
            "songpu_water_level_m",
            "huangdu_water_level_m",
            "songpu_flushing_potential",
            "songpu_resuspension_potential",
        ]
        for feature in hydro_features:
            state[feature] = float(row.get(feature, 0.0))

        # Detect scenario type based on conditions
        state["scenario_type"] = self._detect_scenario(state)

        return state

    def _detect_scenario(self, state: dict[str, Any]) -> str:
        """
        Detect scenario type based on state conditions.

        Returns:
            Scenario type: "s1_external_input", "s2_internal_release", "s3_algae_bloom", "s4_chronic_combo"
        """
        rainfall_3d = state.get("rainfall_3d", 0.0)
        rainfall_7d = state.get("rainfall_7d", 0.0)
        chlorophyll = state.get("chlorophyll_a", 0.0)
        turbidity_7d_mean = state.get("turbidity_7d_mean", 0.0)

        # Scenario 1: External input (high 3-day rainfall)
        if rainfall_3d > 36.0:  # Empirical threshold from project
            return "s1_external_input"

        # Scenario 3: Algae bloom (high chlorophyll + sunlight proxy)
        if chlorophyll > 8.0:  # μg/L threshold
            return "s3_algae_bloom"

        # Scenario 4: Chronic combo (baseline turbidity elevated)
        if turbidity_7d_mean > 3.0:  # NTU threshold, 7 consecutive days
            return "s4_chronic_combo"

        # Scenario 2: Internal release (default for remaining cases)
        return "s2_internal_release"

    def get_date_range(self) -> tuple[str, str]:
        """Get the date range of available data."""
        if self.merged_df.empty:
            return ("", "")
        start_date = self.merged_df.iloc[0]["date"].strftime("%Y-%m-%d")
        end_date = self.merged_df.iloc[-1]["date"].strftime("%Y-%m-%d")
        return start_date, end_date

    def get_total_rows(self) -> int:
        """Get total number of rows in merged dataset."""
        return len(self.merged_df)

    def iterate_date_range(
        self, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """
        Get states for a date range.

        Args:
            start_date: Start date string "YYYY-MM-DD"
            end_date: End date string "YYYY-MM-DD"

        Returns:
            List of state dictionaries for the date range
        """
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        mask = (self.merged_df["date"] >= start_dt) & (self.merged_df["date"] <= end_dt)
        subset = self.merged_df[mask]

        states = []
        for _, row in subset.iterrows():
            states.append(self._row_to_state(row))

        return states
