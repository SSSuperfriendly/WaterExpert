from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any, Iterable

from backend.app.config import Settings


CATALOG_RELATIVE_PATH = Path("data") / "full_station_database" / "station_catalog.csv"
DATABASE_RELATIVE_PATH = (
    Path("data") / "full_station_database" / "water_quality_daily_all_stations_with_secchi.csv"
)
DEFAULT_QUERY_LIMIT = 200
DEFAULT_SERIES_LIMIT = 180

DATABASE_COLUMNS: tuple[str, ...] = (
    "date",
    "station_code",
    "station_name",
    "river",
    "water_temp",
    "ph",
    "dissolved_oxygen",
    "conductivity",
    "turbidity",
    "tp",
    "tn",
    "secchi_depth_sd_m",
    "water_quality_class",
)

NUMERIC_FIELDS: tuple[str, ...] = (
    "water_temp",
    "ph",
    "dissolved_oxygen",
    "conductivity",
    "turbidity",
    "tp",
    "tn",
    "secchi_depth_sd_m",
)

INDICATOR_LABELS = {
    "water_temp": "水温",
    "ph": "pH",
    "dissolved_oxygen": "溶解氧",
    "conductivity": "电导率",
    "turbidity": "浊度",
    "tp": "总磷",
    "tn": "总氮",
    "secchi_depth_sd_m": "透明度",
}


@dataclass(frozen=True)
class StationRecord:
    station_code: str
    station_name: str
    province: str
    city: str
    basin: str
    river: str
    longitude: str
    latitude: str
    start_date: str
    end_date: str
    raw_rows: str
    daily_rows: str
    is_available: str
    availability_note: str
    source_file: str

    def as_dict(self) -> dict[str, str]:
        return {
            "station_code": self.station_code,
            "station_name": self.station_name,
            "province": self.province,
            "city": self.city,
            "basin": self.basin,
            "river": self.river,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "raw_rows": self.raw_rows,
            "daily_rows": self.daily_rows,
            "is_available": self.is_available,
            "availability_note": self.availability_note,
            "source_file": self.source_file,
        }


def _to_float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _to_int(value: Any) -> int | None:
    numeric = _to_float(value)
    return None if numeric is None else int(numeric)


def _safe_divide(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


def _quantile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    return lower_value + (upper_value - lower_value) * (position - lower)


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) < 2 or len(left) != len(right):
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum((left_value - left_mean) * (right_value - right_mean) for left_value, right_value in zip(left, right))
    left_denom = math.sqrt(sum((value - left_mean) ** 2 for value in left))
    right_denom = math.sqrt(sum((value - right_mean) ** 2 for value in right))
    denominator = left_denom * right_denom
    if denominator == 0:
        return None
    return numerator / denominator


class DataExplorerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._catalog_path = settings.runtime_root / CATALOG_RELATIVE_PATH
        self._database_path = settings.runtime_root / DATABASE_RELATIVE_PATH

    @cached_property
    def _stations(self) -> list[StationRecord]:
        stations: list[StationRecord] = []
        with self._catalog_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                stations.append(
                    StationRecord(
                        station_code=str(row.get("station_code", "")),
                        station_name=str(row.get("station_name", "")),
                        province=str(row.get("province", "")),
                        city=str(row.get("city", "")),
                        basin=str(row.get("basin", "")),
                        river=str(row.get("river", "")),
                        longitude=str(row.get("longitude", "")),
                        latitude=str(row.get("latitude", "")),
                        start_date=str(row.get("start_date", "")),
                        end_date=str(row.get("end_date", "")),
                        raw_rows=str(row.get("raw_rows", "")),
                        daily_rows=str(row.get("daily_rows", "")),
                        is_available=str(row.get("is_available", "")),
                        availability_note=str(row.get("availability_note", "")),
                        source_file=str(row.get("source_file", "")),
                    )
                )
        return stations

    def _iter_database_rows(self) -> Iterable[dict[str, str]]:
        with self._database_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield {key: str(value or "") for key, value in row.items()}

    def database_stations(self) -> list[dict[str, str]]:
        return [station.as_dict() for station in self._stations]

    def database_summary(self) -> dict[str, Any]:
        total_records = sum(_to_int(station.daily_rows) or 0 for station in self._stations)
        date_start = min((station.start_date for station in self._stations if station.start_date), default="")
        date_end = max((station.end_date for station in self._stations if station.end_date), default="")
        return {
            "total_records": total_records,
            "total_stations": len(self._stations),
            "date_start": date_start,
            "date_end": date_end,
            "key_indicators": [
                {"key": field, "label": INDICATOR_LABELS.get(field, field)}
                for field in NUMERIC_FIELDS
            ],
        }

    def _match_row(
        self,
        row: dict[str, str],
        *,
        station_code: str | None,
        keyword: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> bool:
        if station_code and row.get("station_code") != station_code:
            return False
        row_date = row.get("date", "")
        if start_date and row_date and row_date < start_date:
            return False
        if end_date and row_date and row_date > end_date:
            return False
        if keyword:
            normalized_keyword = keyword.lower()
            haystack = " ".join(
                [
                    row.get("station_code", ""),
                    row.get("station_name", ""),
                    row.get("city", ""),
                    row.get("river", ""),
                    row.get("basin", ""),
                ]
            ).lower()
            if normalized_keyword not in haystack:
                return False
        return True

    def query_records(
        self,
        *,
        station_code: str | None = None,
        keyword: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        matched_rows: list[dict[str, Any]] = []
        matched_count = 0
        stations_seen: set[str] = set()
        turbidity_values: list[float] = []
        secchi_values: list[float] = []
        first_date = ""
        last_date = ""
        safe_limit = max(1, limit)
        safe_offset = max(0, offset)

        for row in self._iter_database_rows():
            if not self._match_row(
                row,
                station_code=station_code,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
            ):
                continue

            matched_count += 1
            stations_seen.add(row.get("station_code", ""))
            row_date = row.get("date", "")
            if row_date:
                if not first_date or row_date < first_date:
                    first_date = row_date
                if not last_date or row_date > last_date:
                    last_date = row_date

            turbidity = _to_float(row.get("turbidity"))
            if turbidity is not None:
                turbidity_values.append(turbidity)
            secchi = _to_float(row.get("secchi_depth_sd_m"))
            if secchi is not None:
                secchi_values.append(secchi)

            if matched_count <= safe_offset:
                continue

            if len(matched_rows) < safe_limit:
                matched_rows.append({column: row.get(column, "") for column in DATABASE_COLUMNS})

        page = (safe_offset // safe_limit) + 1
        total_pages = max(1, math.ceil(matched_count / safe_limit)) if matched_count else 1
        return {
            "filters": {
                "station_code": station_code or "",
                "keyword": keyword or "",
                "start_date": start_date or "",
                "end_date": end_date or "",
                "limit": safe_limit,
                "offset": safe_offset,
            },
            "matched_rows": matched_count,
            "returned_rows": len(matched_rows),
            "rows": matched_rows,
            "pagination": {
                "page": page,
                "page_size": safe_limit,
                "offset": safe_offset,
                "total_pages": total_pages,
                "has_previous": safe_offset > 0,
                "has_next": safe_offset + len(matched_rows) < matched_count,
                "showing_from": safe_offset + 1 if matched_rows else 0,
                "showing_to": safe_offset + len(matched_rows),
            },
            "summary": {
                "station_count": len([item for item in stations_seen if item]),
                "date_start": first_date,
                "date_end": last_date,
                "mean_turbidity": fmean(turbidity_values) if turbidity_values else None,
                "mean_secchi_depth": fmean(secchi_values) if secchi_values else None,
            },
        }

    def _rows_for_station(self, station_code: str) -> list[dict[str, str]]:
        rows = [
            row
            for row in self._iter_database_rows()
            if row.get("station_code") == station_code
        ]
        rows.sort(key=lambda item: item.get("date", ""))
        return rows

    def _station_profile(self, station_code: str) -> dict[str, str]:
        for station in self._stations:
            if station.station_code == station_code:
                return station.as_dict()
        return {"station_code": station_code, "station_name": station_code}

    def preprocessing_summary(self, station_code: str) -> dict[str, Any]:
        rows = self._rows_for_station(station_code)
        total_rows = len(rows)
        profiles: list[dict[str, Any]] = []
        total_missing = 0
        total_outliers = 0

        for field in NUMERIC_FIELDS:
            numeric_values: list[float] = []
            values_with_missing: list[float | None] = []
            for row in rows:
                numeric = _to_float(row.get(field))
                values_with_missing.append(numeric)
                if numeric is not None:
                    numeric_values.append(numeric)
            missing_count = sum(1 for value in values_with_missing if value is None)
            total_missing += missing_count
            sorted_values = sorted(numeric_values)
            q1 = _quantile(sorted_values, 0.25)
            q3 = _quantile(sorted_values, 0.75)
            iqr = (q3 - q1) if q1 is not None and q3 is not None else None
            if iqr is not None:
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                outlier_count = sum(
                    1 for value in numeric_values if value < lower_bound or value > upper_bound
                )
            else:
                outlier_count = 0
            total_outliers += outlier_count
            std_value = pstdev(numeric_values) if len(numeric_values) >= 2 else None
            profile = {
                "feature": field,
                "feature_label": INDICATOR_LABELS.get(field, field),
                "valid_count": len(numeric_values),
                "missing_count": missing_count,
                "missing_rate": _safe_divide(missing_count, total_rows),
                "mean": fmean(numeric_values) if numeric_values else None,
                "median": median(numeric_values) if numeric_values else None,
                "min": min(numeric_values) if numeric_values else None,
                "max": max(numeric_values) if numeric_values else None,
                "std": std_value,
                "outlier_count": outlier_count,
                "outlier_rate": _safe_divide(outlier_count, len(numeric_values)),
                "standardization_hint": self._standardization_hint(std_value, outlier_count, len(numeric_values)),
            }
            profiles.append(profile)

        recommendations = self._preprocess_recommendations(
            total_rows=total_rows,
            total_missing=total_missing,
            total_outliers=total_outliers,
            profiles=profiles,
        )

        return {
            "station": self._station_profile(station_code),
            "rows_analyzed": total_rows,
            "date_start": rows[0].get("date", "") if rows else "",
            "date_end": rows[-1].get("date", "") if rows else "",
            "total_missing_cells": total_missing,
            "total_outlier_flags": total_outliers,
            "feature_profiles": profiles,
            "recommendations": recommendations,
        }

    def _standardization_hint(
        self, std_value: float | None, outlier_count: int, valid_count: int
    ) -> str:
        if valid_count == 0:
            return "缺少有效值，需先补齐数据。"
        if outlier_count > 0:
            return "建议先处理异常值，再进行标准化。"
        if std_value is None or std_value == 0:
            return "波动很小，可保持原尺度。"
        return "建议进行 Z-score 标准化。"

    def _preprocess_recommendations(
        self,
        *,
        total_rows: int,
        total_missing: int,
        total_outliers: int,
        profiles: list[dict[str, Any]],
    ) -> list[str]:
        if total_rows == 0:
            return ["当前站点暂无可分析数据。"]

        recommendations: list[str] = []
        if total_missing:
            recommendations.append("存在缺失值，建议按时间序列先做插值或邻近站点补齐。")
        if total_outliers:
            recommendations.append("存在 IQR 异常值标记，建议结合监测日志核对后再入模。")
        wide_features = [
            item["feature_label"]
            for item in profiles
            if item.get("std") is not None and float(item["std"]) > 10
        ]
        if wide_features:
            recommendations.append(
                "以下指标波动范围较大，建议标准化后再参与透明度预测："
                + "、".join(wide_features[:4])
            )
        if not recommendations:
            recommendations.append("当前样本质量较稳定，可直接进入建模或可视化分析。")
        recommendations.append("当前页面展示的是吴淞口/全站数据库样本级预处理摘要，不替代研究脚本的正式训练前处理。")
        return recommendations

    def visualization_payload(
        self,
        *,
        station_code: str,
        indicator: str,
        limit: int = DEFAULT_SERIES_LIMIT,
    ) -> dict[str, Any]:
        rows = self._rows_for_station(station_code)
        indicator_key = indicator if indicator in NUMERIC_FIELDS else "turbidity"
        trimmed_rows = rows[-max(1, limit) :]
        series = []
        indicator_values: list[float] = []
        for row in trimmed_rows:
            value = _to_float(row.get(indicator_key))
            series.append({"date": row.get("date", ""), "value": value})
            if value is not None:
                indicator_values.append(value)

        latest_value = indicator_values[-1] if indicator_values else None
        previous_value = indicator_values[-2] if len(indicator_values) >= 2 else None
        delta = None
        if latest_value is not None and previous_value is not None:
            delta = latest_value - previous_value

        correlations = self._correlations(trimmed_rows, indicator_key)
        return {
            "station": self._station_profile(station_code),
            "indicator": indicator_key,
            "indicator_label": INDICATOR_LABELS.get(indicator_key, indicator_key),
            "series": series,
            "stats": {
                "mean": fmean(indicator_values) if indicator_values else None,
                "min": min(indicator_values) if indicator_values else None,
                "max": max(indicator_values) if indicator_values else None,
                "latest": latest_value,
                "delta": delta,
            },
            "correlations": correlations,
            "available_indicators": [
                {"key": field, "label": INDICATOR_LABELS.get(field, field)}
                for field in NUMERIC_FIELDS
            ],
        }

    def _correlations(
        self, rows: list[dict[str, str]], indicator_key: str
    ) -> list[dict[str, Any]]:
        correlations: list[dict[str, Any]] = []
        for candidate in NUMERIC_FIELDS:
            if candidate == indicator_key:
                continue
            left_values: list[float] = []
            right_values: list[float] = []
            for row in rows:
                left = _to_float(row.get(indicator_key))
                right = _to_float(row.get(candidate))
                if left is None or right is None:
                    continue
                left_values.append(left)
                right_values.append(right)
            coefficient = _pearson(left_values, right_values)
            if coefficient is None:
                continue
            correlations.append(
                {
                    "feature": candidate,
                    "feature_label": INDICATOR_LABELS.get(candidate, candidate),
                    "correlation": coefficient,
                    "sample_size": len(left_values),
                }
            )
        correlations.sort(key=lambda item: abs(float(item["correlation"])), reverse=True)
        return correlations[:6]
