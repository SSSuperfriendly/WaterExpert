"""Data acceptance: turn an uploaded file into a modelable, graded dataset."""

from backend.app.services.ingestion.pipeline import (
    CANONICAL_DATA_FILENAME,
    FIELD_DICTIONARY_FILENAME,
    LINEAGE_FILENAME,
    QUALITY_REPORT_FILENAME,
    SUPPORTED_SUFFIXES,
    IngestionError,
    IngestionResult,
    StageReport,
    persist_result,
    run_ingestion,
)
from backend.app.services.ingestion.quality import (
    MIN_MODELABLE_ROWS,
    FieldQuality,
    QualityReport,
    UnitConversion,
    grade_report,
)
from backend.app.services.ingestion.schema_registry import (
    DATASET_SPECS,
    SUPPORTED_DATA_TYPES,
    DatasetSpec,
    FieldSpec,
    field_dictionary,
    get_spec,
)

__all__ = [
    "CANONICAL_DATA_FILENAME",
    "DATASET_SPECS",
    "FIELD_DICTIONARY_FILENAME",
    "LINEAGE_FILENAME",
    "MIN_MODELABLE_ROWS",
    "QUALITY_REPORT_FILENAME",
    "SUPPORTED_DATA_TYPES",
    "SUPPORTED_SUFFIXES",
    "DatasetSpec",
    "FieldQuality",
    "FieldSpec",
    "IngestionError",
    "IngestionResult",
    "QualityReport",
    "StageReport",
    "UnitConversion",
    "field_dictionary",
    "get_spec",
    "grade_report",
    "persist_result",
    "run_ingestion",
]
