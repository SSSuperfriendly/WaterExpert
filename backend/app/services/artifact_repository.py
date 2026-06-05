from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import Settings

DEFAULT_STATION_CODE = "2586"
PRODUCT_MODE = "integrated-runtime"
FRONTEND_MODE = "software-with-embedded-waterexpert-core"
ARTIFACT_SCOPE_JOB = "job-scoped"
ARTIFACT_SCOPE_DEFAULT = "integrated-default"
DEFAULT_PREVIEW_LIMIT = 16
BOUNDARY_PREVIEW_LIMIT = 120
AGENT_CONTEXT_PATH = "agent/agent_context.json"
SCENARIO_TRIAGE_PATH = "agent/scenario_triage.json"
RESPONSE_PLAYBOOK_PATH = "agent/response_playbook.json"
METRICS_PATH = "metrics/metrics.json"
BEST_MODEL_SUMMARY_PATH = "metrics/best_model_summary.json"
MODEL_COMPARISON_PATH = "metrics/model_comparison.csv"
PREDICTIONS_PATH = "predictions/predictions.csv"
DIAGNOSIS_FACTOR_SUMMARY_PATH = "diagnosis/mscim_turbidity_factor_diagnosis_summary.json"
DIAGNOSIS_DOMAIN_PATH = "diagnosis/mscim_turbidity_domain_diagnosis.csv"
PROCESS_DECOMPOSITION_PATH = "diagnosis/cmfbe_process_decomposition_summary.csv"
THRESHOLD_SUMMARY_PATH = "thresholds/cmfbe_threshold_summary.csv"
THRESHOLD_BY_CONTEXT_PATH = "thresholds/cmfbe_thresholds_by_context.csv"
THRESHOLD_KG_PATH = "thresholds/mechanism_parameter_threshold_kg.json"
BOUNDARY_SUMMARY_PATH = "boundary/boundary_detection_summary.json"
BOUNDARY_PREDICTIONS_PATH = "boundary/boundary_predictions.csv"
BOUNDARY_LABEL_GENERATION_PATH = "boundary/boundary_label_generation_summary.json"
BOUNDARY_LABEL_CSV_PATH = "boundary/merged_boundary_labels.csv"
SOBOL_PATH = "sensitivity/cmfbe_sobol_indices.json"
COUNTERFACTUAL_PATH = "counterfactual/cmfbe_counterfactual_summary.csv"
JOINT_COUNTERFACTUAL_PATH = "counterfactual/cmfbe_joint_counterfactual_summary.csv"
CMFBE_MODEL_NAME = "cmfbe_stgcn"
TEST_SPLIT_NAME = "test"


class ArtifactReadError(ValueError):
    """Raised when an artifact exists but is malformed or unreadable."""


@dataclass(frozen=True)
class ProcessSpec:
    key: str
    label: str
    direction: str


PROCESS_SPECS: tuple[ProcessSpec, ...] = (
    ProcessSpec("runoff_source", "Runoff Input", "source"),
    ProcessSpec("erosion_source", "Resuspension", "source"),
    ProcessSpec("tidal_source", "Tidal Retention", "source"),
    ProcessSpec("phytoplankton_source", "Ecological Growth", "source"),
    ProcessSpec("krone_deposition_sink", "Deposition Flocculation", "sink"),
    ProcessSpec("flushing_sink", "Flushing Export", "sink"),
    ProcessSpec("purification_sink", "Self Purification", "sink"),
)

PREDICTION_SERIES_COLUMNS: tuple[str, ...] = (
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
)


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

    def _artifact_scope(self) -> str:
        return (
            ARTIFACT_SCOPE_JOB
            if self.outputs_root != self.settings.outputs_root
            else ARTIFACT_SCOPE_DEFAULT
        )

    def _artifact_path(self, relative_path: str) -> Path:
        return self.outputs_root / relative_path

    def _read_json(self, relative_path: str) -> dict[str, Any]:
        path = self._artifact_path(relative_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
            raise ArtifactReadError(f"Invalid JSON artifact at {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ArtifactReadError(f"JSON artifact must decode to an object: {path}")
        return payload

    def _read_csv(self, relative_path: str) -> pd.DataFrame:
        path = self._artifact_path(relative_path)
        try:
            return pd.read_csv(path)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ArtifactReadError(f"Failed to read CSV artifact at {path}: {exc}") from exc

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

    def _required_source_paths(self) -> list[Path]:
        return [
            self.runtime_root / "src" / "water_ai" / "__init__.py",
            self._artifact_path(AGENT_CONTEXT_PATH),
            self._artifact_path(METRICS_PATH),
            self._artifact_path(PREDICTIONS_PATH),
            self.config_path,
        ]

    def assert_source_ready(self) -> None:
        missing = [str(path) for path in self._required_source_paths() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Missing integrated runtime assets: " + ", ".join(missing)
            )

    def _dataset_summary(self) -> dict[str, Any]:
        metrics = self._read_json(METRICS_PATH)
        return metrics["data"]["dataset_summary"]

    def _scope_note(self, dataset_summary: dict[str, Any]) -> str:
        notes = dataset_summary.get("notes", {})
        if isinstance(notes, dict):
            return str(notes.get("current_scope", ""))
        return ""

    def _best_model_summary(self, agent_context: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._read_json(BEST_MODEL_SUMMARY_PATH)
        except FileNotFoundError:
            fallback = agent_context.get("best_model_summary", {})
            return fallback if isinstance(fallback, dict) else {}

    def _station_profile(self, dataset_summary: dict[str, Any]) -> dict[str, Any]:
        station = dataset_summary["water_station"]
        hydrodynamics = dataset_summary.get("hydrodynamics", {})
        return {
            "station_code": DEFAULT_STATION_CODE,
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
        }

    def _process_decomposition_summary(self) -> pd.DataFrame:
        path = self._artifact_path(PROCESS_DECOMPOSITION_PATH)
        if path.exists():
            return self._read_csv(PROCESS_DECOMPOSITION_PATH)

        predictions = self._read_csv(PREDICTIONS_PATH)
        filtered = self._cmfbe_test_predictions(predictions)
        rows: list[dict[str, Any]] = []
        for spec in PROCESS_SPECS:
            if spec.key not in filtered.columns:
                continue
            series = pd.to_numeric(filtered[spec.key], errors="coerce").dropna()
            if series.empty:
                continue
            rows.append(
                {
                    "process_key": spec.key,
                    "process_label": spec.label,
                    "direction": spec.direction,
                    "mean_contribution": float(series.mean()),
                    "std_contribution": float(series.std(ddof=0)),
                    "max_contribution": float(series.max()),
                }
            )
        return pd.DataFrame(rows)

    def _cmfbe_test_predictions(self, predictions: pd.DataFrame) -> pd.DataFrame:
        filtered = predictions.copy()
        if "model" in filtered.columns:
            cmfbe = filtered[filtered["model"] == CMFBE_MODEL_NAME].copy()
            if not cmfbe.empty:
                filtered = cmfbe
        if "split" in filtered.columns:
            test_rows = filtered[filtered["split"] == TEST_SPLIT_NAME].copy()
            if not test_rows.empty:
                filtered = test_rows
        return filtered

    def artifact_manifest(self) -> dict[str, str]:
        return {
            "outputs_root": str(self.outputs_root),
            "agent_context": str(self._artifact_path(AGENT_CONTEXT_PATH)),
            "scenario_triage": str(self._artifact_path(SCENARIO_TRIAGE_PATH)),
            "response_playbook": str(self._artifact_path(RESPONSE_PLAYBOOK_PATH)),
            "predictions": str(self._artifact_path(PREDICTIONS_PATH)),
            "metrics": str(self._artifact_path(METRICS_PATH)),
            "diagnosis": str(
                self._artifact_path(DIAGNOSIS_FACTOR_SUMMARY_PATH)
            ),
            "thresholds": str(
                self._artifact_path(THRESHOLD_SUMMARY_PATH)
            ),
            "boundary_summary": str(
                self._artifact_path(BOUNDARY_SUMMARY_PATH)
            ),
            "sensitivity": str(
                self._artifact_path(SOBOL_PATH)
            ),
            "runtime_config": str(self.config_path),
            "pipeline_script": str(
                self.runtime_root / "scripts" / "run_full_pipeline.py"
            ),
        }

    def stations(self) -> list[dict[str, Any]]:
        dataset_summary = self._dataset_summary()
        station_profile = self._station_profile(dataset_summary)
        return [
            {
                **station_profile,
                "scope": self._scope_note(dataset_summary),
            }
        ]

    def metadata(self) -> dict[str, Any]:
        self.assert_source_ready()
        dashboard = self.dashboard()
        return {
            "app_name": self.settings.app_name,
            "product_mode": PRODUCT_MODE,
            "prototype_scope": dashboard["prototype_scope"],
            "runtime_root": str(self.runtime_root),
            "outputs_root": str(self.outputs_root),
            "frontend_mode": FRONTEND_MODE,
            "station_profile": dashboard["station_profile"],
            "artifact_manifest": self.artifact_manifest(),
            "guardrails": dashboard["guardrails"],
            "artifact_scope": self._artifact_scope(),
        }

    def dashboard(self) -> dict[str, Any]:
        agent_context = self._read_json(AGENT_CONTEXT_PATH)
        best_model = self._best_model_summary(agent_context)
        dataset_summary = self._dataset_summary()

        return {
            "product_name": "WaterExpert Software",
            "algorithm_core": "embedded WaterExpert runtime",
            "prototype_scope": self._scope_note(dataset_summary),
            "purpose": agent_context.get("purpose"),
            "artifact_scope": self._artifact_scope(),
            "artifact_root": str(self.outputs_root),
            "station_profile": self._station_profile(dataset_summary),
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

    def _available_values(self, frame: pd.DataFrame, column: str) -> list[str]:
        if column not in frame.columns:
            return []
        return sorted(frame[column].dropna().astype(str).unique().tolist())

    def _selected_prediction_model(
        self,
        requested_model: str | None,
        agent_context: dict[str, Any],
        available_models: list[str],
    ) -> str:
        default_model = None
        best_model_summary = agent_context.get("best_model_summary", {})
        if isinstance(best_model_summary, dict):
            default_model = best_model_summary.get("best_test_turbidity_model")
        selected_model = requested_model or default_model or (available_models[0] if available_models else None)
        if not selected_model:
            raise ValueError("No prediction model could be selected from the current artifacts.")
        if available_models and selected_model not in available_models:
            raise ValueError(f"Unsupported model '{selected_model}'.")
        return selected_model

    def _normalize_prediction_columns(self, frame: pd.DataFrame) -> pd.DataFrame:
        normalized = frame.copy()
        for column in PREDICTION_SERIES_COLUMNS:
            if column not in normalized.columns:
                normalized[column] = None
        if "target_date" in normalized.columns:
            normalized["target_date"] = pd.to_datetime(
                normalized["target_date"],
                errors="coerce",
            )
            normalized = normalized.sort_values("target_date")
        return normalized

    def predictions(self, model: str | None, split: str = "test") -> dict[str, Any]:
        predictions = self._read_csv(PREDICTIONS_PATH)
        available_models = self._available_values(predictions, "model")
        available_splits = self._available_values(predictions, "split")
        agent_context = self._read_json(AGENT_CONTEXT_PATH)
        selected_model = self._selected_prediction_model(
            model,
            agent_context,
            available_models,
        )
        if available_splits and split not in available_splits:
            raise ValueError(f"Unsupported split '{split}'.")

        filtered = predictions.copy()
        if "model" in filtered.columns:
            filtered = filtered[filtered["model"] == selected_model].copy()
        if "split" in filtered.columns:
            filtered = filtered[filtered["split"] == split].copy()
        filtered = self._normalize_prediction_columns(filtered)
        comparison = self._read_csv(MODEL_COMPARISON_PATH)
        summary_lookup = agent_context.get("test_models", {})
        return {
            "available_models": available_models,
            "available_splits": available_splits,
            "selected_model": selected_model,
            "selected_split": split,
            "summary": summary_lookup.get(selected_model, {}),
            "model_comparison": self._records(comparison),
            "series": self._records(filtered[list(PREDICTION_SERIES_COLUMNS)]),
        }

    def diagnostics(self) -> dict[str, Any]:
        factor_summary = self._read_json(DIAGNOSIS_FACTOR_SUMMARY_PATH)
        domain_summary = self._read_csv(DIAGNOSIS_DOMAIN_PATH)
        return {
            "factor_summary": factor_summary,
            "process_decomposition": self._records(
                self._process_decomposition_summary()
            ),
            "domain_diagnosis": self._records(domain_summary),
        }

    def scenario_triage(self) -> dict[str, Any]:
        return self._read_json(SCENARIO_TRIAGE_PATH)

    def response_playbook(self) -> dict[str, Any]:
        return self._read_json(RESPONSE_PLAYBOOK_PATH)

    def _filter_threshold_graph(
        self, knowledge_graph: dict[str, Any], feature: str
    ) -> dict[str, Any]:
        return {
            **knowledge_graph,
            "threshold_nodes": [
                node
                for node in knowledge_graph.get("threshold_nodes", [])
                if node.get("feature") == feature
            ],
        }

    def thresholds(self, feature: str | None = None) -> dict[str, Any]:
        summary = self._read_csv(THRESHOLD_SUMMARY_PATH)
        by_context = self._read_csv(THRESHOLD_BY_CONTEXT_PATH)
        knowledge_graph = self._read_json(THRESHOLD_KG_PATH)

        if feature:
            summary = summary[summary["feature"] == feature].copy()
            by_context = by_context[by_context["feature"] == feature].copy()
            knowledge_graph = self._filter_threshold_graph(knowledge_graph, feature)

        return {
            "threshold_semantics": knowledge_graph.get("threshold_semantics"),
            "risk_snapshot": knowledge_graph.get("risk_snapshot", {}),
            "summary": self._records(summary),
            "by_context": self._records(by_context),
            "knowledge_graph": knowledge_graph,
        }

    def _boundary_label_summary(
        self, summary: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return self._read_json(BOUNDARY_LABEL_GENERATION_PATH)
        except FileNotFoundError:
            overall = summary.get("overall", {}).get("test", {})
            return {
                "status": summary.get("status", "evaluated"),
                "source_path": str(self._artifact_path(BOUNDARY_LABEL_CSV_PATH)),
                "labeled_days": overall.get("labeled_samples"),
                "positive_days": None,
                "label_column": "boundary_label",
                "notes": [
                    "Boundary label generation summary was not present for this artifact set.",
                    "The current boundary label is a raster-derived proxy label, not a validated physical boundary product.",
                ],
            }

    def boundary(self) -> dict[str, Any]:
        summary = self._read_json(BOUNDARY_SUMMARY_PATH)
        predictions = self._read_csv(BOUNDARY_PREDICTIONS_PATH)
        if "split" in predictions.columns:
            predictions = predictions[predictions["split"] == TEST_SPLIT_NAME].copy()
        if "target_date" in predictions.columns:
            predictions["target_date"] = pd.to_datetime(
                predictions["target_date"],
                errors="coerce",
            )
            predictions = predictions.sort_values("target_date")
        return {
            "summary": summary,
            "label_generation_summary": self._boundary_label_summary(summary),
            "prediction_preview": self._records(
                predictions,
                limit=BOUNDARY_PREVIEW_LIMIT,
            ),
        }

    def sensitivity(self) -> dict[str, Any]:
        sobol = self._read_json(SOBOL_PATH)
        counterfactual = self._read_csv(COUNTERFACTUAL_PATH)
        joint_counterfactual = self._read_csv(JOINT_COUNTERFACTUAL_PATH)
        return {
            "sobol": sobol,
            "counterfactual": self._records(counterfactual, limit=DEFAULT_PREVIEW_LIMIT),
            "joint_counterfactual": self._records(
                joint_counterfactual,
                limit=DEFAULT_PREVIEW_LIMIT,
            ),
        }
