"""Data-quality metrics and grading.

Review item 3 lists exactly what an import must be able to report once it
finishes. This module computes that list and turns it into a grade, so the data
asset centre can answer "is this data modelable, and if not, why not?".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.app.domain.codes import MODELABLE_GRADES, QualityGrade

#: A dataset needs at least this many aligned rows before it is worth modelling.
MIN_MODELABLE_ROWS = 30

#: Grade thresholds, evaluated in order. The first band a dataset fails to clear
#: determines its grade.
GRADE_THRESHOLDS: tuple[tuple[QualityGrade, float, float, float], ...] = (
    # (grade, max missing rate, max out-of-range rate, max duplicate rate)
    (QualityGrade.A, 0.05, 0.01, 0.01),
    (QualityGrade.B, 0.20, 0.05, 0.05),
    (QualityGrade.C, 0.40, 0.15, 0.15),
)


@dataclass
class UnitConversion:
    """One recorded unit change, so a reviewer can audit what was rescaled."""

    column: str
    canonical_field: str
    source_unit: str
    target_unit: str
    factor: float
    converted_values: int


@dataclass
class FieldQuality:
    canonical: str
    label: str
    source_column: str | None
    present: bool
    total_rows: int
    missing_count: int
    missing_rate: float
    out_of_range_count: int
    unparseable_count: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None


@dataclass
class QualityReport:
    """Everything review item 3 requires an import to be able to answer."""

    error_count: int = 0
    warning_count: int = 0
    missing_rate: float = 0.0
    duplicate_rows: int = 0
    out_of_range_count: int = 0
    unparseable_count: int = 0

    source_rows: int = 0
    mapped_rows: int = 0
    aligned_rows: int = 0
    modelable_rows: int = 0

    time_coverage_start: str | None = None
    time_coverage_end: str | None = None
    time_expected_days: int = 0
    time_present_days: int = 0
    time_gap_days: int = 0

    station_coverage: list[str] = field(default_factory=list)

    unit_conversions: list[UnitConversion] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    field_quality: list[FieldQuality] = field(default_factory=list)

    grade: QualityGrade = QualityGrade.D
    modelable: bool = False
    blocking_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["grade"] = str(self.grade)
        return payload


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def grade_report(report: QualityReport) -> QualityReport:
    """Assign ``grade``, ``modelable`` and ``blocking_reasons`` in place.

    Grading is deliberately conservative: any hard blocker (missing required
    field, no aligned rows, too few rows) forces grade D regardless of how clean
    the remaining columns look, because a dataset the model cannot consume is not
    a "mostly fine" dataset.
    """
    blocking: list[str] = []

    if report.missing_required_fields:
        blocking.append("missing_required_fields")
    if report.aligned_rows <= 0:
        blocking.append("no_aligned_rows")
    elif report.modelable_rows < MIN_MODELABLE_ROWS:
        blocking.append("insufficient_modelable_rows")

    duplicate_rate = _rate(report.duplicate_rows, report.source_rows)
    out_of_range_rate = _rate(report.out_of_range_count, max(report.aligned_rows, 1))

    if blocking:
        report.grade = QualityGrade.D
    else:
        report.grade = QualityGrade.D
        for grade, max_missing, max_out_of_range, max_duplicate in GRADE_THRESHOLDS:
            if (
                report.missing_rate <= max_missing
                and out_of_range_rate <= max_out_of_range
                and duplicate_rate <= max_duplicate
            ):
                report.grade = grade
                break

    report.blocking_reasons = blocking
    report.modelable = not blocking and report.grade in MODELABLE_GRADES
    if not report.modelable and not blocking:
        report.blocking_reasons = ["quality_grade_below_threshold"]
    return report
