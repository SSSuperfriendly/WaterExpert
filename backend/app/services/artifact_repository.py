from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import Settings


class ArtifactRepository:
    def __init__(
        self,
        settings: Settings,
        outputs_root: Path | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self._outputs_root = (
            Path(outputs_root).resolve() if outputs_root is not None else settings.outputs_root
        )
        self._config_path = (
            Path(config_path).resolve() if config_path is not None else settings.default_config_path
        )

    @property
    def runtime_root(self) -> Path:
        return self.settings.runtime_root

    @property
    def outputs_root(self) -> Path:
        return self._outputs_root

    @property
    def config_path(self) -> Path:
        return self._config_path

    def scoped(
        self,
        outputs_root: Path | None = None,
        config_path: Path | None = None,
    ) -> "ArtifactRepository":
        return ArtifactRepository(
            settings=self.settings,
            outputs_root=outputs_root or self.outputs_root,
            config_path=config_path or self.config_path,
        )

    def assert_source_ready(self) -> None:
        required = [
            self.runtime_root / "src" / "water_ai" / "__init__.py",
            self.outputs_root / "agent" / "agent_context.json",
            self.outputs_root / "metrics" / "metrics.json",
            self.outputs_root / "predictions" / "predictions.csv",
            self.config_path,
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Missing integrated runtime assets: " + ", ".join(missing)
            )

    def _read_json(self, relative_path: str) -> dict[str, Any]:
        path = self.outputs_root / relative_path
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_csv(self, relative_path: str) -> pd.DataFrame:
        path = self.outputs_root / relative_path
        return pd.read_csv(path)

    def _records(
        self, frame: pd.DataFrame, limit: int | None = None
    ) -> list[dict[str, Any]]:
        if limit is not None:
            frame = frame.head(limit)
        return json.loads(
            frame.to_json(
                orient="records", force_ascii=False, date_format="iso"
            )
        )

    def _process_decomposition_summary(self) -> pd.DataFrame:
        path = self.outputs_root / "diagnosis" / "cmfbe_process_decomposition_summary.csv"
        if path.exists():
            return pd.read_csv(path)

        predictions = self._read_csv("predictions/predictions.csv")
        if "model" in predictions.columns:
            filtered = predictions[predictions["model"] == "cmfbe_stgcn"].copy()
        else:
            filtered = predictions.copy()
        if "split" in filtered.columns:
            test_filtered = filtered[filtered["split"] == "test"].copy()
            if not test_filtered.empty:
                filtered = test_filtered

        process_specs = [
            ("runoff_source", "径流输入", "source"),
            ("erosion_source", "再悬浮", "source"),
            ("tidal_source", "潮汐滞留", "source"),
            ("phytoplankton_source", "生态增殖", "source"),
            ("krone_deposition_sink", "沉降絮凝", "sink"),
            ("flushing_sink", "冲刷外输", "sink"),
            ("purification_sink", "自净恢复", "sink"),
        ]
        rows: list[dict[str, Any]] = []
        for column, label, direction in process_specs:
            if column not in filtered.columns:
                continue
            series = pd.to_numeric(filtered[column], errors="coerce").dropna()
            if series.empty:
                continue
            rows.append(
                {
                    "process_key": column,
                    "process_label": label,
                    "direction": direction,
                    "mean_contribution": float(series.mean()),
                    "std_contribution": float(series.std(ddof=0)),
                    "max_contribution": float(series.max()),
                }
            )
        return pd.DataFrame(rows)

    def artifact_manifest(self) -> dict[str, str]:
        return {
            "outputs_root": str(self.outputs_root),
            "agent_context": str(self.outputs_root / "agent" / "agent_context.json"),
            "scenario_triage": str(self.outputs_root / "agent" / "scenario_triage.json"),
            "response_playbook": str(self.outputs_root / "agent" / "response_playbook.json"),
            "predictions": str(self.outputs_root / "predictions" / "predictions.csv"),
            "metrics": str(self.outputs_root / "metrics" / "metrics.json"),
            "diagnosis": str(
                self.outputs_root
                / "diagnosis"
                / "mscim_turbidity_factor_diagnosis_summary.json"
            ),
            "thresholds": str(
                self.outputs_root / "thresholds" / "cmfbe_threshold_summary.csv"
            ),
            "boundary_summary": str(
                self.outputs_root / "boundary" / "boundary_detection_summary.json"
            ),
            "sensitivity": str(
                self.outputs_root / "sensitivity" / "cmfbe_sobol_indices.json"
            ),
            "runtime_config": str(self.config_path),
            "pipeline_script": str(
                self.runtime_root / "scripts" / "run_full_pipeline.py"
            ),
        }

    def stations(self) -> list[dict[str, Any]]:
        metrics = self._read_json("metrics/metrics.json")
        dataset_summary = metrics["data"]["dataset_summary"]
        station = dataset_summary["water_station"]
        return [
            {
                "station_code": "2586",
                "station_name": station.get("station_name"),
                "river": station.get("river"),
                "basin": station.get("basin"),
                "longitude": station.get("longitude"),
                "latitude": station.get("latitude"),
                "date_start": station.get("start_date"),
                "date_end": station.get("end_date"),
                "daily_rows": station.get("daily_rows"),
                "scope": dataset_summary["notes"]["current_scope"],
            }
        ]

    def metadata(self) -> dict[str, Any]:
        self.assert_source_ready()
        dashboard = self.dashboard()
        return {
            "app_name": self.settings.app_name,
            "product_mode": "integrated-runtime",
            "prototype_scope": dashboard["prototype_scope"],
            "runtime_root": str(self.runtime_root),
            "outputs_root": str(self.outputs_root),
            "frontend_mode": "software-with-embedded-waterexpert-core",
            "station_profile": dashboard["station_profile"],
            "artifact_manifest": self.artifact_manifest(),
            "guardrails": dashboard["guardrails"],
            "artifact_scope": "job-scoped" if self.outputs_root != self.settings.outputs_root else "integrated-default",
        }

    def dashboard(self) -> dict[str, Any]:
        agent_context = self._read_json("agent/agent_context.json")
        metrics = self._read_json("metrics/metrics.json")
        best_model = self._read_json("metrics/best_model_summary.json")
        dataset_summary = metrics["data"]["dataset_summary"]
        station = dataset_summary["water_station"]
        hydrodynamics = dataset_summary.get("hydrodynamics", {})

        return {
            "product_name": "WaterExpert Software",
            "algorithm_core": "embedded WaterExpert runtime",
            "prototype_scope": dataset_summary["notes"]["current_scope"],
            "purpose": agent_context.get("purpose"),
            "artifact_scope": "job-scoped" if self.outputs_root != self.settings.outputs_root else "integrated-default",
            "artifact_root": str(self.outputs_root),
            "station_profile": {
                "station_code": "2586",
                "station_name": station.get("station_name"),
                "river": station.get("river"),
                "basin": station.get("basin"),
                "longitude": station.get("longitude"),
                "latitude": station.get("latitude"),
                "daily_rows": station.get("daily_rows"),
                "date_start": station.get("start_date"),
                "date_end": station.get("end_date"),
                "matched_model_rows": dataset_summary.get("rows_after_merge"),
                "hydrodynamic_reference_station": hydrodynamics.get(
                    "recommended_primary_station_for_current_model"
                ),
            },
            "best_model_summary": best_model,
            "test_models": agent_context.get("test_models", {}),
            "threshold_risk_snapshot": agent_context.get(
                "threshold_risk_snapshot", {}
            ),
            "scenario_counts": agent_context.get("scenario_counts", {}),
            "high_priority_days": agent_context.get(
                "scenario_high_priority_days", []
            ),
            "recommended_agent_queries": agent_context.get(
                "recommended_agent_queries", []
            ),
            "guardrails": agent_context.get("guardrails", []),
        }

    def predictions(self, model: str | None, split: str = "test") -> dict[str, Any]:
        predictions = self._read_csv("predictions/predictions.csv")
        available_models = sorted(
            predictions["model"].dropna().unique().tolist()
        )
        available_splits = sorted(
            predictions["split"].dropna().unique().tolist()
        )

        agent_context = self._read_json("agent/agent_context.json")
        selected_model = (
            model
            or agent_context["best_model_summary"]["best_test_turbidity_model"]
        )
        if selected_model not in available_models:
            raise ValueError(f"Unsupported model '{selected_model}'.")
        if split not in available_splits:
            raise ValueError(f"Unsupported split '{split}'.")

        filtered = predictions[
            (predictions["model"] == selected_model)
            & (predictions["split"] == split)
        ].copy()
        if "target_date" in filtered.columns:
            filtered["target_date"] = pd.to_datetime(filtered["target_date"])
            filtered = filtered.sort_values("target_date")
        comparison = self._read_csv("metrics/model_comparison.csv")
        series_columns = [
            "target_date",
            "actual_turbidity",
            "predicted_turbidity",
            "actual_clearness",
            "predicted_clearness",
            "predicted_self_purification_failure_prob",
            "predicted_turbidity_surge_prob",
            "predicted_critical_transition_prob",
            "predicted_boundary_probability",
            "velocity_proxy",
            "bed_shear_proxy",
            "erosion_source",
            "runoff_source",
            "phytoplankton_source",
            "flushing_sink",
            "purification_sink",
        ]
        for column in series_columns:
            if column not in filtered.columns:
                filtered[column] = None

        summary_lookup = agent_context.get("test_models", {})
        return {
            "available_models": available_models,
            "available_splits": available_splits,
            "selected_model": selected_model,
            "selected_split": split,
            "summary": summary_lookup.get(selected_model, {}),
            "model_comparison": self._records(comparison),
            "series": self._records(filtered[series_columns]),
        }

    def diagnostics(self) -> dict[str, Any]:
        factor_summary = self._read_json(
            "diagnosis/mscim_turbidity_factor_diagnosis_summary.json"
        )
        process_summary = self._process_decomposition_summary()
        domain_summary = self._read_csv(
            "diagnosis/mscim_turbidity_domain_diagnosis.csv"
        )
        return {
            "factor_summary": factor_summary,
            "process_decomposition": self._records(process_summary),
            "domain_diagnosis": self._records(domain_summary),
        }

    def scenario_triage(self) -> dict[str, Any]:
        return self._read_json("agent/scenario_triage.json")

    def response_playbook(self) -> dict[str, Any]:
        return self._read_json("agent/response_playbook.json")

    def thresholds(self, feature: str | None = None) -> dict[str, Any]:
        summary = self._read_csv("thresholds/cmfbe_threshold_summary.csv")
        by_context = self._read_csv(
            "thresholds/cmfbe_thresholds_by_context.csv"
        )
        knowledge_graph = self._read_json(
            "thresholds/mechanism_parameter_threshold_kg.json"
        )

        if feature:
            summary = summary[summary["feature"] == feature].copy()
            by_context = by_context[by_context["feature"] == feature].copy()
            knowledge_graph["threshold_nodes"] = [
                node
                for node in knowledge_graph.get("threshold_nodes", [])
                if node.get("feature") == feature
            ]

        return {
            "threshold_semantics": knowledge_graph.get("threshold_semantics"),
            "risk_snapshot": knowledge_graph.get("risk_snapshot", {}),
            "summary": self._records(summary),
            "by_context": self._records(by_context),
            "knowledge_graph": knowledge_graph,
        }

    def boundary(self) -> dict[str, Any]:
        summary = self._read_json("boundary/boundary_detection_summary.json")
        predictions = self._read_csv("boundary/boundary_predictions.csv")
        try:
            label_summary = self._read_json(
                "boundary/boundary_label_generation_summary.json"
            )
        except FileNotFoundError:
            overall = summary.get("overall", {}).get("test", {})
            label_summary = {
                "status": summary.get("status", "evaluated"),
                "source_path": str(
                    self.outputs_root / "boundary" / "merged_boundary_labels.csv"
                ),
                "labeled_days": overall.get("labeled_samples"),
                "positive_days": None,
                "label_column": "boundary_label",
                "notes": [
                    "Boundary label generation summary was not present for this artifact set.",
                    "The current boundary label is a raster-derived proxy label, not a validated physical boundary product.",
                ],
            }
        if "split" in predictions.columns:
            predictions = predictions[predictions["split"] == "test"].copy()
        if "target_date" in predictions.columns:
            predictions["target_date"] = pd.to_datetime(
                predictions["target_date"]
            )
            predictions = predictions.sort_values("target_date")
        return {
            "summary": summary,
            "label_generation_summary": label_summary,
            "prediction_preview": self._records(predictions, limit=120),
        }

    def sensitivity(self) -> dict[str, Any]:
        sobol = self._read_json("sensitivity/cmfbe_sobol_indices.json")
        counterfactual = self._read_csv(
            "counterfactual/cmfbe_counterfactual_summary.csv"
        )
        joint_counterfactual = self._read_csv(
            "counterfactual/cmfbe_joint_counterfactual_summary.csv"
        )
        return {
            "sobol": sobol,
            "counterfactual": self._records(counterfactual, limit=16),
            "joint_counterfactual": self._records(
                joint_counterfactual, limit=16
            ),
        }
