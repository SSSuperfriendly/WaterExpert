"""The data acceptance chain: uploaded → validated → mapped → cleaned → aligned → accepted/rejected.

Review item 3: "导入成功不等于数据可用". Each stage below either advances the
dataset or stops it with a machine-readable reason, so the data asset centre can
always answer *这份数据是否已经进入模型输入？如果没有，卡在哪一步？*

The pipeline is pure with respect to the filesystem apart from one write: the
accepted, canonicalized frame is persisted so the runtime has a modelable file
rather than a copy of whatever the user uploaded.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.domain.codes import INGESTION_STAGE_ORDER, IngestionStage
from backend.app.services.ingestion.quality import (
    FieldQuality,
    QualityReport,
    UnitConversion,
    grade_report,
)
from backend.app.services.ingestion.schema_registry import (
    DatasetSpec,
    FieldSpec,
    extract_unit,
    get_spec,
    normalize_column,
    normalize_unit,
)

SUPPORTED_SUFFIXES: frozenset[str] = frozenset({".csv", ".xls", ".xlsx", ".json", ".parquet"})
CANONICAL_DATA_FILENAME = "data.csv"
QUALITY_REPORT_FILENAME = "quality_report.json"
FIELD_DICTIONARY_FILENAME = "field_dictionary.json"
LINEAGE_FILENAME = "lineage.json"

#: A row is treated as a units header when at least this share of its non-empty
#: cells look like unit tokens rather than data.
UNIT_ROW_TOKEN_SHARE = 0.6

_YEAR_ALIASES = {"year", "年", "年份"}
_MONTH_ALIASES = {"mon", "month", "月", "月份"}
_DAY_ALIASES = {"day", "日", "日期号"}


@dataclass
class StageReport:
    """Outcome of one stage in the chain."""

    stage: IngestionStage
    ok: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stage"] = str(self.stage)
        return payload


@dataclass
class IngestionResult:
    data_type: str
    final_stage: IngestionStage
    accepted: bool
    stages: list[StageReport]
    quality: QualityReport
    frame: pd.DataFrame | None = None

    @property
    def blocked_at(self) -> IngestionStage | None:
        """The stage that stopped the dataset, or ``None`` when it was accepted."""
        if self.accepted:
            return None
        for report in self.stages:
            if not report.ok:
                return report.stage
        return self.final_stage

    def as_dict(self) -> dict[str, Any]:
        return {
            "data_type": self.data_type,
            "final_stage": str(self.final_stage),
            "accepted": self.accepted,
            "blocked_at": str(self.blocked_at) if self.blocked_at else None,
            "stage_order": [str(stage) for stage in INGESTION_STAGE_ORDER],
            "stages": [report.as_dict() for report in self.stages],
            "quality": self.quality.as_dict(),
        }


class IngestionError(ValueError):
    """The source file could not be read at all."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _read_raw(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise IngestionError(f"Unsupported file format '{suffix}'.")
    try:
        if suffix == ".csv":
            return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if suffix == ".parquet":
            return pd.read_parquet(path).astype(str)
        if suffix in {".xls", ".xlsx"}:
            return pd.read_excel(path, dtype=str).fillna("")
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            payload = payload.get("records", payload.get("data", [payload]))
        if not isinstance(payload, list):
            raise IngestionError("JSON payload must be a list of records.")
        return pd.DataFrame(payload).astype(str)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(f"{type(exc).__name__}: {exc}") from exc


def _looks_like_unit_token(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith("(") or text.startswith("（"):
        return True
    return normalize_unit(text) in {
        "mg/l",
        "ug/l",
        "us/cm",
        "ms/cm",
        "ntu",
        "℃",
        "°c",
        "m",
        "cm",
        "mm",
        "m3/s",
        "m3s",
        "hpa",
        "%",
        "无量纲",
        "类别",
        "cells/l",
    }


def _split_units_row(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Detach a units row (row 0) when the file carries one.

    ``data/raw/wusongkou_water_quality_2586.csv`` puts ``(℃)``, ``(mg/L)`` … on
    the first data row. Treating that as data would poison every column, so it is
    lifted into a per-column unit hint instead.
    """
    if frame.empty:
        return frame, {}
    first = frame.iloc[0]
    populated = [str(value).strip() for value in first if str(value).strip()]
    if not populated:
        return frame, {}
    token_share = sum(1 for value in populated if _looks_like_unit_token(value)) / len(populated)
    if token_share < UNIT_ROW_TOKEN_SHARE:
        return frame, {}
    units = {
        str(column): str(first[column]).strip().strip("()（）")
        for column in frame.columns
        if str(first[column]).strip()
    }
    return frame.iloc[1:].reset_index(drop=True), units


def _synthesize_date(frame: pd.DataFrame) -> pd.Series | None:
    """Build a date column from separate Year / Mon / Day columns."""
    lookup = {normalize_column(column): column for column in frame.columns}
    year = next((lookup[key] for key in _YEAR_ALIASES if key in lookup), None)
    month = next((lookup[key] for key in _MONTH_ALIASES if key in lookup), None)
    day = next((lookup[key] for key in _DAY_ALIASES if key in lookup), None)
    if not (year and month and day):
        return None
    parts = pd.DataFrame(
        {
            "year": pd.to_numeric(frame[year], errors="coerce"),
            "month": pd.to_numeric(frame[month], errors="coerce"),
            "day": pd.to_numeric(frame[day], errors="coerce"),
        }
    )
    return pd.to_datetime(parts, errors="coerce")


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def _stage_validated(
    frame: pd.DataFrame, spec: DatasetSpec, unit_hints: dict[str, str]
) -> StageReport:
    errors: list[str] = []
    warnings: list[str] = []

    if frame.empty:
        errors.append("file_is_empty")

    marker_hits = [
        marker
        for marker in spec.preprocessor_required_markers
        if any(marker in str(column) for column in frame.columns)
    ]
    if marker_hits:
        errors.append("requires_dedicated_preprocessor")
        if spec.preprocessor_hint:
            warnings.append(spec.preprocessor_hint)

    resolvable = {
        item.canonical for column in frame.columns if (item := spec.find_field(column))
    }
    if _synthesize_date(frame) is not None:
        resolvable.add(spec.time_field.canonical)

    missing_required = [
        item.canonical for item in spec.required_fields if item.canonical not in resolvable
    ]
    if missing_required:
        errors.append("missing_required_fields")

    return StageReport(
        stage=IngestionStage.VALIDATED,
        ok=not errors,
        metrics={
            "source_rows": int(len(frame)),
            "source_columns": int(len(frame.columns)),
            "resolvable_fields": sorted(resolvable),
            "missing_required_fields": missing_required,
            "unit_hints": unit_hints,
        },
        errors=errors,
        warnings=warnings,
    )


def _stage_mapped(
    frame: pd.DataFrame, spec: DatasetSpec, unit_hints: dict[str, str]
) -> tuple[pd.DataFrame, StageReport, list[UnitConversion]]:
    """Rename source columns to canonical names and convert units."""
    mapped = pd.DataFrame(index=frame.index)
    conversions: list[UnitConversion] = []
    unmapped: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    resolved: dict[str, str] = {}

    for column in frame.columns:
        target = spec.find_field(column)
        if target is None:
            unmapped.append(str(column))
            continue
        if target.canonical in mapped.columns:
            warnings.append(f"duplicate_source_column_for:{target.canonical}")
            continue

        series = frame[column]
        if target.kind == "numeric":
            numeric = pd.to_numeric(
                series.astype(str).str.strip().replace({"": None}), errors="coerce"
            )
            source_unit = unit_hints.get(str(column)) or extract_unit(str(column))
            factor = target.conversion_factor(source_unit)
            if factor is None:
                errors.append(f"unconvertible_unit:{target.canonical}:{source_unit}")
                continue
            if factor != 1.0:
                converted = int(numeric.notna().sum())
                numeric = numeric * factor
                conversions.append(
                    UnitConversion(
                        column=str(column),
                        canonical_field=target.canonical,
                        source_unit=str(source_unit),
                        target_unit=str(target.unit or ""),
                        factor=float(factor),
                        converted_values=converted,
                    )
                )
            mapped[target.canonical] = numeric
        else:
            mapped[target.canonical] = series.astype(str).str.strip().replace({"": None})
        resolved[str(column)] = target.canonical

    time_column = spec.time_field.canonical
    if time_column not in mapped.columns:
        synthesized = _synthesize_date(frame)
        if synthesized is not None:
            mapped[time_column] = synthesized
            warnings.append("date_synthesized_from_year_month_day")

    return (
        mapped,
        StageReport(
            stage=IngestionStage.MAPPED,
            ok=not errors,
            metrics={
                "mapped_columns": resolved,
                "unmapped_columns": unmapped,
                "unit_conversions": [asdict(item) for item in conversions],
            },
            errors=errors,
            warnings=warnings,
        ),
        conversions,
    )


def _stage_cleaned(
    frame: pd.DataFrame, spec: DatasetSpec
) -> tuple[pd.DataFrame, StageReport, list[FieldQuality]]:
    """Coerce types, null out-of-range values, and drop duplicate rows."""
    cleaned = frame.copy()
    profiles: list[FieldQuality] = []
    out_of_range_total = 0
    unparseable_total = 0

    # A row carrying a date but no measurement at all is padding, not a missing
    # measurement. `wusongkou_boundary_labels.csv` is 891 rows of which 643 are
    # date placeholders from the 7-day raster sampling stride; counting them as
    # missing data would report a 72% missing rate for a file that is actually
    # complete over the days it claims to cover.
    key_columns = {spec.time_field.canonical}
    if spec.station_field:
        key_columns.add(spec.station_field.canonical)
    measurement_columns = [
        column for column in cleaned.columns if column not in key_columns
    ]
    empty_rows = 0
    if measurement_columns:
        populated = cleaned[measurement_columns].notna().any(axis=1)
        empty_rows = int((~populated).sum())
        cleaned = cleaned[populated].copy()

    total_rows = int(len(cleaned))

    for item in spec.all_fields:
        if item.kind == "datetime":
            continue
        present = item.canonical in cleaned.columns
        if not present:
            profiles.append(
                FieldQuality(
                    canonical=item.canonical,
                    label=item.label,
                    source_column=None,
                    present=False,
                    total_rows=total_rows,
                    missing_count=total_rows,
                    missing_rate=1.0 if total_rows else 0.0,
                    out_of_range_count=0,
                    unparseable_count=0,
                )
            )
            continue

        series = cleaned[item.canonical]
        out_of_range = 0
        unparseable = 0
        if item.kind == "numeric":
            numeric = pd.to_numeric(series, errors="coerce")
            unparseable = int((series.notna() & numeric.isna()).sum())
            unparseable_total += unparseable
            if item.minimum is not None or item.maximum is not None:
                mask = pd.Series(False, index=numeric.index)
                if item.minimum is not None:
                    mask |= numeric < item.minimum
                if item.maximum is not None:
                    mask |= numeric > item.maximum
                mask = mask.fillna(False).astype(bool)
                out_of_range = int(mask.sum())
                out_of_range_total += out_of_range
                # Out-of-range values are nulled, not clipped: a 12000 NTU
                # reading is a sensor fault, and clipping it to the ceiling
                # would launder bad data into the model as a plausible extreme.
                numeric = numeric.mask(mask)
            cleaned[item.canonical] = numeric
            series = numeric

        missing = int(series.isna().sum())
        numeric_view = pd.to_numeric(series, errors="coerce") if item.kind == "numeric" else None
        profiles.append(
            FieldQuality(
                canonical=item.canonical,
                label=item.label,
                source_column=item.canonical,
                present=True,
                total_rows=total_rows,
                missing_count=missing,
                missing_rate=(missing / total_rows) if total_rows else 0.0,
                out_of_range_count=out_of_range,
                unparseable_count=unparseable,
                minimum=(
                    float(numeric_view.min()) if numeric_view is not None and numeric_view.notna().any() else None
                ),
                maximum=(
                    float(numeric_view.max()) if numeric_view is not None and numeric_view.notna().any() else None
                ),
                mean=(
                    float(numeric_view.mean()) if numeric_view is not None and numeric_view.notna().any() else None
                ),
            )
        )

    before = len(cleaned)
    cleaned = cleaned.drop_duplicates()
    duplicates = before - len(cleaned)

    return (
        cleaned.reset_index(drop=True),
        StageReport(
            stage=IngestionStage.CLEANED,
            ok=True,
            metrics={
                "rows_in": before + empty_rows,
                "rows_out": int(len(cleaned)),
                "empty_rows_dropped": empty_rows,
                "duplicate_rows_dropped": duplicates,
                "out_of_range_nulled": out_of_range_total,
                "unparseable_values": unparseable_total,
            },
        ),
        profiles,
    )


def _stage_aligned(
    frame: pd.DataFrame, spec: DatasetSpec
) -> tuple[pd.DataFrame, StageReport]:
    """Parse the time column, collapse to the target granularity, match stations."""
    errors: list[str] = []
    warnings: list[str] = []
    time_column = spec.time_field.canonical

    if time_column not in frame.columns:
        return frame, StageReport(
            stage=IngestionStage.ALIGNED,
            ok=False,
            errors=["missing_time_column"],
        )

    aligned = frame.copy()
    parsed = pd.to_datetime(aligned[time_column], errors="coerce")
    unparseable_dates = int(parsed.isna().sum())
    aligned[time_column] = parsed.dt.normalize()
    aligned = aligned[aligned[time_column].notna()].copy()

    if aligned.empty:
        return aligned, StageReport(
            stage=IngestionStage.ALIGNED,
            ok=False,
            metrics={"unparseable_dates": unparseable_dates},
            errors=["no_parseable_dates"],
        )

    station_column = spec.station_field.canonical if spec.station_field else None
    group_keys = [time_column]
    if station_column and station_column in aligned.columns:
        aligned[station_column] = aligned[station_column].astype(str).str.strip()
        group_keys.append(station_column)
    elif station_column:
        warnings.append("station_column_absent_treated_as_single_station")

    aggregation = {
        item.canonical: item.aggregation
        for item in spec.all_fields
        if item.canonical in aligned.columns and item.canonical not in group_keys
    }
    rows_before = int(len(aligned))
    if aggregation:
        collapsed = aligned.groupby(group_keys, as_index=False, dropna=False).agg(aggregation)
    else:
        collapsed = aligned.drop_duplicates(subset=group_keys).reset_index(drop=True)
    collapsed = collapsed.sort_values(group_keys).reset_index(drop=True)

    coverage_start = collapsed[time_column].min()
    coverage_end = collapsed[time_column].max()
    present_days = int(collapsed[time_column].dt.normalize().nunique())
    expected_days = int((coverage_end - coverage_start).days) + 1 if present_days else 0
    gap_days = max(expected_days - present_days, 0)
    if gap_days:
        warnings.append(f"date_gaps:{gap_days}")

    stations = (
        sorted(collapsed[station_column].dropna().astype(str).unique().tolist())
        if station_column and station_column in collapsed.columns
        else []
    )

    return (
        collapsed,
        StageReport(
            stage=IngestionStage.ALIGNED,
            ok=not errors,
            metrics={
                "granularity": spec.granularity,
                "rows_in": rows_before,
                "rows_out": int(len(collapsed)),
                "collapsed_rows": rows_before - int(len(collapsed)),
                "unparseable_dates": unparseable_dates,
                "coverage_start": coverage_start.date().isoformat() if present_days else None,
                "coverage_end": coverage_end.date().isoformat() if present_days else None,
                "expected_days": expected_days,
                "present_days": present_days,
                "gap_days": gap_days,
                "stations": stations,
            },
            errors=errors,
            warnings=warnings,
        ),
    )


def _modelable_rows(frame: pd.DataFrame, spec: DatasetSpec) -> int:
    """Rows where every required non-time field actually has a value."""
    required = [
        item.canonical
        for item in spec.required_fields
        if item.kind != "datetime" and item.canonical in frame.columns
    ]
    if not required:
        return int(len(frame))
    return int(frame[required].notna().all(axis=1).sum())


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_ingestion(source_path: Path, data_type: str) -> IngestionResult:
    """Run the full acceptance chain over ``source_path``.

    Stops at the first failing stage; the returned :class:`IngestionResult`
    always names where it stopped and why.
    """
    spec = get_spec(data_type)
    stages: list[StageReport] = []
    quality = QualityReport()

    try:
        raw = _read_raw(source_path)
    except IngestionError as exc:
        stages.append(
            StageReport(
                stage=IngestionStage.UPLOADED,
                ok=False,
                errors=[f"unreadable_source:{exc}"],
            )
        )
        quality.error_count = 1
        return IngestionResult(
            data_type=spec.data_type,
            final_stage=IngestionStage.REJECTED,
            accepted=False,
            stages=stages,
            quality=grade_report(quality),
        )

    raw, unit_hints = _split_units_row(raw)
    quality.source_rows = int(len(raw))
    stages.append(
        StageReport(
            stage=IngestionStage.UPLOADED,
            ok=True,
            metrics={
                "filename": source_path.name,
                "size_bytes": source_path.stat().st_size if source_path.exists() else 0,
                "rows": quality.source_rows,
                "columns": int(len(raw.columns)),
                "units_row_detected": bool(unit_hints),
            },
        )
    )

    def finish(final_stage: IngestionStage, accepted: bool, frame: pd.DataFrame | None = None):
        quality.error_count = sum(len(report.errors) for report in stages)
        quality.warning_count = sum(len(report.warnings) for report in stages)
        return IngestionResult(
            data_type=spec.data_type,
            final_stage=final_stage,
            accepted=accepted,
            stages=stages,
            quality=grade_report(quality),
            frame=frame,
        )

    validated = _stage_validated(raw, spec, unit_hints)
    stages.append(validated)
    quality.missing_required_fields = list(validated.metrics.get("missing_required_fields", []))
    if not validated.ok:
        return finish(IngestionStage.REJECTED, False)

    mapped_frame, mapped, conversions = _stage_mapped(raw, spec, unit_hints)
    stages.append(mapped)
    quality.unit_conversions = conversions
    quality.unmapped_columns = list(mapped.metrics.get("unmapped_columns", []))
    quality.mapped_rows = int(len(mapped_frame))
    if not mapped.ok:
        return finish(IngestionStage.REJECTED, False)

    cleaned_frame, cleaned, profiles = _stage_cleaned(mapped_frame, spec)
    stages.append(cleaned)
    quality.field_quality = profiles
    quality.duplicate_rows = int(cleaned.metrics.get("duplicate_rows_dropped", 0))
    quality.out_of_range_count = int(cleaned.metrics.get("out_of_range_nulled", 0))
    quality.unparseable_count = int(cleaned.metrics.get("unparseable_values", 0))

    aligned_frame, aligned = _stage_aligned(cleaned_frame, spec)
    stages.append(aligned)
    quality.aligned_rows = int(len(aligned_frame))
    quality.time_coverage_start = aligned.metrics.get("coverage_start")
    quality.time_coverage_end = aligned.metrics.get("coverage_end")
    quality.time_expected_days = int(aligned.metrics.get("expected_days", 0))
    quality.time_present_days = int(aligned.metrics.get("present_days", 0))
    quality.time_gap_days = int(aligned.metrics.get("gap_days", 0))
    quality.station_coverage = list(aligned.metrics.get("stations", []))
    if not aligned.ok:
        return finish(IngestionStage.REJECTED, False)

    quality.modelable_rows = _modelable_rows(aligned_frame, spec)
    tracked = [
        item.canonical
        for item in spec.all_fields
        if item.kind == "numeric" and item.canonical in aligned_frame.columns
    ]
    if tracked and len(aligned_frame):
        quality.missing_rate = float(
            aligned_frame[tracked].isna().sum().sum() / (len(aligned_frame) * len(tracked))
        )

    graded = grade_report(quality)
    accepted = graded.modelable
    stages.append(
        StageReport(
            stage=IngestionStage.ACCEPTED if accepted else IngestionStage.REJECTED,
            ok=accepted,
            metrics={
                "grade": str(graded.grade),
                "modelable_rows": graded.modelable_rows,
                "missing_rate": round(graded.missing_rate, 6),
            },
            errors=list(graded.blocking_reasons) if not accepted else [],
        )
    )
    return finish(
        IngestionStage.ACCEPTED if accepted else IngestionStage.REJECTED,
        accepted,
        aligned_frame,
    )


def persist_result(result: IngestionResult, version_root: Path, lineage: dict[str, Any]) -> dict[str, str]:
    """Write the canonical frame, quality report, field dictionary and lineage."""
    from backend.app.services.ingestion.schema_registry import field_dictionary

    version_root.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    if result.frame is not None and not result.frame.empty:
        data_path = version_root / CANONICAL_DATA_FILENAME
        result.frame.to_csv(data_path, index=False, encoding="utf-8-sig")
        written["data"] = str(data_path)

    quality_path = version_root / QUALITY_REPORT_FILENAME
    quality_path.write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    written["quality_report"] = str(quality_path)

    dictionary_path = version_root / FIELD_DICTIONARY_FILENAME
    dictionary_path.write_text(
        json.dumps(field_dictionary(result.data_type), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    written["field_dictionary"] = str(dictionary_path)

    lineage_path = version_root / LINEAGE_FILENAME
    lineage_path.write_text(
        json.dumps(lineage, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    written["lineage"] = str(lineage_path)

    return written
