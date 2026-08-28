from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.app.domain.codes import IngestionStage, QualityGrade
from backend.app.services.ingestion import (
    field_dictionary,
    get_spec,
    persist_result,
    run_ingestion,
)
from backend.app.services.ingestion.schema_registry import extract_unit, normalize_column


def _write_csv(root: Path, name: str, rows: list[dict[str, object]]) -> Path:
    path = root / name
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _daily_water_quality_rows(count: int, **overrides: object) -> list[dict[str, object]]:
    """One reading per distinct day, so nothing collapses during alignment."""
    dates = pd.date_range("2024-01-01", periods=count, freq="D")
    rows = []
    for index, day in enumerate(dates):
        row: dict[str, object] = {
            "监测时间": f"{day.date().isoformat()} 08:00",
            "站点": "2586",
            "浊度": 30.0 + index,
            "水温": 15.0,
            "pH": 7.5,
            "溶解氧": 8.0,
        }
        row.update(overrides)
        rows.append(row)
    return rows


class ColumnNormalizationTest(unittest.TestCase):
    def test_normalize_column_strips_bom_units_and_case(self) -> None:
        self.assertEqual(normalize_column("﻿监测时间"), "监测时间")
        self.assertEqual(normalize_column("溶解氧(mg/L)"), "溶解氧")
        self.assertEqual(normalize_column("Station_Id_C"), "station_id_c")

    def test_extract_unit_reads_parenthesised_and_suffix_forms(self) -> None:
        self.assertEqual(extract_unit("溶解氧(mg/L)"), "mg/l")
        self.assertEqual(extract_unit("电导率(μS/cm)"), "us/cm")
        self.assertEqual(extract_unit("huangdu_flow_m3s"), "m3s")
        self.assertIsNone(extract_unit("turbidity"))

    def test_dimensionless_unit_is_not_a_mismatch(self) -> None:
        ph = get_spec("water_quality").find_field("pH")
        assert ph is not None
        self.assertEqual(ph.conversion_factor("无量纲"), 1.0)
        self.assertEqual(ph.conversion_factor(None), 1.0)
        self.assertIsNone(ph.conversion_factor("mg/L"))


class IngestionPipelineTest(unittest.TestCase):
    def test_accepts_clean_daily_water_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_csv(root, "wq.csv", _daily_water_quality_rows(40))
            result = run_ingestion(source, "water_quality")

            self.assertTrue(result.accepted)
            self.assertEqual(result.final_stage, IngestionStage.ACCEPTED)
            self.assertIsNone(result.blocked_at)
            self.assertEqual(result.quality.grade, QualityGrade.A)
            self.assertEqual(result.quality.station_coverage, ["2586"])
            self.assertIsNotNone(result.frame)
            self.assertIn("turbidity", result.frame.columns)

    def test_converts_units_and_records_the_conversion(self) -> None:
        """A file in mg/L-equivalents must be rescaled, not accepted as-is."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = _daily_water_quality_rows(40)
            for row in rows:
                row["溶解氧(μg/L)"] = 8000.0  # 8 mg/L expressed in μg/L
                row.pop("溶解氧")
            source = _write_csv(root, "wq_units.csv", rows)

            result = run_ingestion(source, "water_quality")

            self.assertTrue(result.accepted)
            conversions = {item.canonical_field: item for item in result.quality.unit_conversions}
            self.assertIn("dissolved_oxygen", conversions)
            conversion = conversions["dissolved_oxygen"]
            self.assertEqual(conversion.source_unit, "ug/l")
            self.assertAlmostEqual(conversion.factor, 0.001)
            self.assertEqual(conversion.converted_values, 40)
            self.assertAlmostEqual(float(result.frame["dissolved_oxygen"].iloc[0]), 8.0)

    def test_rejects_unconvertible_unit_at_mapped_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = _daily_water_quality_rows(40)
            for row in rows:
                row["浊度(mg/L)"] = 30.0
                row.pop("浊度")
            source = _write_csv(root, "wq_bad_unit.csv", rows)

            result = run_ingestion(source, "water_quality")

            self.assertFalse(result.accepted)
            self.assertEqual(result.blocked_at, IngestionStage.MAPPED)
            mapped = next(s for s in result.stages if s.stage == IngestionStage.MAPPED)
            self.assertTrue(any("unconvertible_unit" in error for error in mapped.errors))

    def test_blocks_at_validated_when_required_field_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{"监测时间": "2024-01-01", "站点": "2586", "水温": 15.0}]
            source = _write_csv(root, "no_turbidity.csv", rows)

            result = run_ingestion(source, "water_quality")

            self.assertFalse(result.accepted)
            self.assertEqual(result.blocked_at, IngestionStage.VALIDATED)
            self.assertIn("turbidity", result.quality.missing_required_fields)

    def test_nulls_out_of_range_values_instead_of_clipping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = _daily_water_quality_rows(40)
            rows[0]["浊度"] = 99999.0  # beyond the 5000 NTU ceiling
            source = _write_csv(root, "wq_outlier.csv", rows)

            result = run_ingestion(source, "water_quality")

            self.assertEqual(result.quality.out_of_range_count, 1)
            self.assertLess(float(result.frame["turbidity"].max()), 5000.0)

    def test_collapses_multiple_readings_per_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {"监测时间": "2024-03-01 04:00", "站点": "2586", "浊度": 10.0},
                {"监测时间": "2024-03-01 16:00", "站点": "2586", "浊度": 20.0},
            ]
            source = _write_csv(root, "wq_intraday.csv", rows)

            result = run_ingestion(source, "water_quality")
            aligned = next(s for s in result.stages if s.stage == IngestionStage.ALIGNED)

            self.assertEqual(aligned.metrics["rows_out"], 1)
            self.assertEqual(aligned.metrics["collapsed_rows"], 1)
            self.assertAlmostEqual(float(result.frame["turbidity"].iloc[0]), 15.0)

    def test_drops_empty_padding_rows_rather_than_counting_them_missing(self) -> None:
        """Date placeholders with no measurement are not missing data."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows: list[dict[str, object]] = [
                {"date": f"2024-01-{day:02d}", "boundary_label": 1.0} for day in range(1, 32)
            ]
            rows.extend({"date": f"2024-02-{day:02d}", "boundary_label": None} for day in range(1, 29))
            source = _write_csv(root, "boundary.csv", rows)

            result = run_ingestion(source, "boundary_labels")
            cleaned = next(s for s in result.stages if s.stage == IngestionStage.CLEANED)

            self.assertEqual(cleaned.metrics["empty_rows_dropped"], 28)
            self.assertEqual(result.quality.aligned_rows, 31)
            self.assertEqual(result.quality.missing_rate, 0.0)

    def test_rejects_hydrodynamics_pivot_report_with_preprocessor_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_csv(root, "pivot.csv", [{"吴淞江 黄渡 站逐日平均流量表": "年份：", "b": 1}])

            result = run_ingestion(source, "hydrodynamics")

            self.assertFalse(result.accepted)
            self.assertEqual(result.blocked_at, IngestionStage.VALIDATED)
            validated = next(s for s in result.stages if s.stage == IngestionStage.VALIDATED)
            self.assertIn("requires_dedicated_preprocessor", validated.errors)
            self.assertTrue(validated.warnings)

    def test_synthesizes_date_from_year_month_day_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {"Year": 2024, "Mon": 5, "Day": day, "平均气温": 20.0, "当天降水量": 1.0}
                for day in range(1, 32)
            ]
            source = _write_csv(root, "weather.csv", rows)

            result = run_ingestion(source, "weather")

            self.assertTrue(result.accepted)
            self.assertEqual(result.quality.time_coverage_start, "2024-05-01")
            self.assertEqual(result.quality.time_coverage_end, "2024-05-31")

    def test_reports_unreadable_source_at_uploaded_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "broken.csv"
            source.write_bytes(b"\xff\xfe\x00 not a csv")

            result = run_ingestion(source, "water_quality")

            self.assertFalse(result.accepted)
            self.assertEqual(result.blocked_at, IngestionStage.UPLOADED)

    def test_too_few_rows_is_a_blocking_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_csv(root, "tiny.csv", _daily_water_quality_rows(3))

            result = run_ingestion(source, "water_quality")

            self.assertFalse(result.accepted)
            self.assertIn("insufficient_modelable_rows", result.quality.blocking_reasons)
            self.assertEqual(result.quality.grade, QualityGrade.D)


class PersistenceTest(unittest.TestCase):
    def test_persist_writes_data_quality_dictionary_and_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_csv(root, "wq.csv", _daily_water_quality_rows(40))
            result = run_ingestion(source, "water_quality")

            version_root = root / "v1"
            written = persist_result(result, version_root, {"source": "unit-test"})

            self.assertEqual(set(written), {"data", "quality_report", "field_dictionary", "lineage"})
            self.assertTrue((version_root / "data.csv").exists())
            report = json.loads((version_root / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["final_stage"], "accepted")
            self.assertEqual(report["stage_order"][0], "uploaded")


class FieldDictionaryTest(unittest.TestCase):
    def test_every_supported_type_exposes_a_dictionary(self) -> None:
        for data_type in ("water_quality", "weather", "hydrodynamics", "boundary_labels"):
            dictionary = field_dictionary(data_type)
            self.assertEqual(dictionary["data_type"], data_type)
            self.assertTrue(dictionary["fields"])
            self.assertTrue(any(item["required"] for item in dictionary["fields"]))


if __name__ == "__main__":
    unittest.main()
