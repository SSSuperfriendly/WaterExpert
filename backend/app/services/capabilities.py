"""The deployment's structured vocabulary.

One place that answers "what exists here?" — data types, models, severities,
indicators, report formats and stations — sourced from the registries that
already own those facts. The frontend renders its selectors from this instead of
hard-coding keys, so registering a new data type or model is a backend change
only, and the platform stays site-agnostic rather than tied to one deployment.
"""

from __future__ import annotations

from backend.app.domain.codes import ModelStage, Severity
from backend.app.domain.models import MODEL_CATALOGUE
from backend.app.services.data_explorer import INDICATOR_LABELS
from backend.app.services.ingestion.schema_registry import (
    DATASET_SPECS,
    DERIVED_DATA_TYPES,
)
from backend.app.services.model_service import MODEL_TRANSITIONS
from backend.app.services.report_builder import REPORT_MEDIA_TYPES


def describe(stations: list[dict[str, str]]) -> dict[str, object]:
    """Assemble the capability payload.

    ``stations`` is injected rather than read here so the caller decides where
    the station catalogue comes from (the database service today, a registry
    tomorrow) without this module growing a data dependency.
    """
    return {
        "data_types": [
            {"key": spec.data_type, "label": spec.label, "derived": False}
            for spec in DATASET_SPECS.values()
        ]
        + [
            {"key": key, "label": key, "derived": True}
            for key in sorted(DERIVED_DATA_TYPES)
        ],
        "models": [
            {
                "key": entry.key,
                "label_code": entry.label_code,
                "required": entry.required,
                "description_code": entry.description_code,
            }
            for entry in MODEL_CATALOGUE
        ],
        "severities": [member.value for member in Severity],
        "report_formats": list(REPORT_MEDIA_TYPES),
        "model_stages": [member.value for member in ModelStage],
        "model_transitions": {
            str(stage): sorted(str(target) for target in targets)
            for stage, targets in MODEL_TRANSITIONS.items()
        },
        "indicators": [
            {"key": key, "label": label} for key, label in INDICATOR_LABELS.items()
        ],
        "stations": stations,
    }
