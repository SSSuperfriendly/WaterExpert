"""Declarative field schemas per data type.

The 2026-08-28 review (item 3) found that "import" meant *copy the file and
count its rows* — no field mapping, no unit conversion, no time alignment. This
module is the mapping table that makes those steps real.

Every alias here was read off an actual file in this repository:

* ``water_quality``   — ``data/raw/wusongkou_water_quality_2586.csv`` (Chinese
  headers plus a units row) and
  ``data/full_station_database/water_quality_daily_all_stations_with_secchi.csv``
  (English headers).
* ``weather``         — ``data/raw/shanghai_weather_daily.csv`` (Year/Mon/Day split
  across three columns).
* ``hydrodynamics``   — ``outputs/hydrodynamics_preprocessed/shanghai_hydrodynamics_daily_wide.csv``.
  The *raw* ``shanghai_hydrodynamics.xls`` is a pivot-table report (year blocks,
  month columns, day rows) and is deliberately not accepted here: it must go
  through the dedicated preprocessor first, and the pipeline says so by name.
* ``boundary_labels`` — ``data/raw/wusongkou_boundary_labels.csv``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal, Mapping

FieldKind = Literal["numeric", "categorical", "datetime"]
Aggregation = Literal["mean", "sum", "max", "min", "first", "last"]

# Unit tokens are compared after this normalization so "μS/cm", "uS/cm" and
# "US/CM" all collide onto one key.
_MICRO_SIGNS = {"µ", "μ"}

#: Tokens that mean "this quantity has no unit". A source file that labels pH as
#: ``(无量纲)`` is agreeing with a spec whose unit is ``None``, not disagreeing
#: with it, so these must not be reported as an unconvertible unit.
DIMENSIONLESS_TOKENS: frozenset[str] = frozenset(
    {"", "无量纲", "dimensionless", "none", "n/a", "-", "1", "类别", "ratio", "pct", "无"}
)


def normalize_unit(token: str) -> str:
    """Normalize a unit string for lookup: NFKC, micro-sign folded, lowercased."""
    normalized = unicodedata.normalize("NFKC", str(token or "")).strip()
    for sign in _MICRO_SIGNS:
        normalized = normalized.replace(sign, "u")
    return normalized.replace(" ", "").lower()


def normalize_column(name: str) -> str:
    """Normalize a column header for alias matching.

    Strips the UTF-8 BOM, NFKC-normalizes full-width characters, drops a
    parenthesised unit suffix, and lowercases ASCII. Chinese headers survive
    intact because only ASCII case folding is applied.
    """
    text = unicodedata.normalize("NFKC", str(name or "")).replace("﻿", "").strip()
    text = re.sub(r"[（(][^)）]*[)）]\s*$", "", text).strip()
    return text.replace(" ", "").replace("\n", "").lower()


def extract_unit(name: str) -> str | None:
    """Pull a unit token out of a column header, e.g. ``溶解氧(mg/L)`` → ``mg/l``.

    Also handles the underscore convention used by the hydrodynamics wide file
    (``huangdu_flow_m3s`` → ``m3s``).
    """
    text = unicodedata.normalize("NFKC", str(name or "")).replace("﻿", "").strip()
    parenthesised = re.search(r"[（(]([^)）]+)[)）]\s*$", text)
    if parenthesised:
        return normalize_unit(parenthesised.group(1))
    underscored = re.search(r"_(m3s|m|mgl|ntu|cms|pct|percent)$", text, flags=re.IGNORECASE)
    if underscored:
        return normalize_unit(underscored.group(1))
    return None


@dataclass(frozen=True)
class FieldSpec:
    """One canonical field: what it is called, what units it accepts, its range."""

    canonical: str
    label: str
    aliases: tuple[str, ...] = ()
    kind: FieldKind = "numeric"
    unit: str | None = None
    #: Recognized source unit (normalized) → factor that converts it to ``unit``.
    unit_conversions: Mapping[str, float] = field(default_factory=dict)
    minimum: float | None = None
    maximum: float | None = None
    required: bool = False
    aggregation: Aggregation = "mean"

    @property
    def normalized_aliases(self) -> frozenset[str]:
        return frozenset(
            normalize_column(alias) for alias in (self.canonical, *self.aliases)
        )

    def conversion_factor(self, source_unit: str | None) -> float | None:
        """Factor converting ``source_unit`` to this field's canonical unit.

        Returns ``1.0`` when the units already match or no unit was detected, and
        ``None`` when the unit is recognizably different but unconvertible — the
        caller records that as a validation error rather than guessing.
        """
        if source_unit is None:
            return 1.0
        normalized = normalize_unit(source_unit)
        if self.unit is None or normalize_unit(self.unit) in DIMENSIONLESS_TOKENS:
            # A dimensionless field accepts a dimensionless label or no label;
            # anything else is a genuine mismatch worth reporting.
            return 1.0 if normalized in DIMENSIONLESS_TOKENS else None
        if normalized in DIMENSIONLESS_TOKENS:
            # The source did not state a unit; assume it already matches.
            return 1.0
        if normalized == normalize_unit(self.unit):
            return 1.0
        factor = self.unit_conversions.get(normalized)
        if factor is not None:
            return float(factor)
        return None


@dataclass(frozen=True)
class DatasetSpec:
    """The full contract for one ``data_type``."""

    data_type: str
    label: str
    time_field: FieldSpec
    fields: tuple[FieldSpec, ...]
    station_field: FieldSpec | None = None
    granularity: str = "daily"
    #: Columns that make a row unique before aggregation.
    notes: tuple[str, ...] = ()
    #: Headers whose presence means the file needs a dedicated preprocessor first.
    preprocessor_required_markers: tuple[str, ...] = ()
    preprocessor_hint: str | None = None

    @property
    def all_fields(self) -> tuple[FieldSpec, ...]:
        extra = (self.station_field,) if self.station_field else ()
        return (self.time_field, *extra, *self.fields)

    @property
    def required_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(spec for spec in self.all_fields if spec.required)

    def find_field(self, column: str) -> FieldSpec | None:
        normalized = normalize_column(column)
        for spec in self.all_fields:
            if normalized in spec.normalized_aliases:
                return spec
        return None


# ---------------------------------------------------------------------------
# Shared field definitions
# ---------------------------------------------------------------------------

DATE_FIELD = FieldSpec(
    canonical="date",
    label="日期",
    aliases=("监测时间", "采样时间", "取样时间", "sample_date", "datetime", "时间", "日期", "观测日期"),
    kind="datetime",
    required=True,
)

STATION_FIELD = FieldSpec(
    canonical="station_code",
    label="站点编码",
    aliases=("站点", "站点编码", "测站编码", "station", "station_id", "station_c", "断面编码"),
    kind="categorical",
    required=True,
    aggregation="first",
)


# ---------------------------------------------------------------------------
# water_quality
# ---------------------------------------------------------------------------

WATER_QUALITY_SPEC = DatasetSpec(
    data_type="water_quality",
    label="水质监测",
    time_field=DATE_FIELD,
    station_field=STATION_FIELD,
    fields=(
        FieldSpec(
            canonical="turbidity",
            label="浊度",
            aliases=("浊度", "turbidity", "turbidity_ntu"),
            unit="NTU",
            unit_conversions={"ntu": 1.0, "ftu": 1.0, "fnu": 1.0},
            minimum=0.0,
            maximum=5000.0,
            required=True,
        ),
        FieldSpec(
            canonical="water_temp",
            label="水温",
            aliases=("水温", "water_temp", "水温度", "temperature"),
            unit="℃",
            unit_conversions={"°c": 1.0, "c": 1.0, "℃": 1.0},
            minimum=-5.0,
            maximum=45.0,
        ),
        FieldSpec(
            canonical="ph",
            label="pH",
            aliases=("ph", "酸碱度", "ph值"),
            unit=None,  # dimensionless; source files label it 无量纲
            minimum=0.0,
            maximum=14.0,
        ),
        FieldSpec(
            canonical="dissolved_oxygen",
            label="溶解氧",
            aliases=("溶解氧", "dissolved_oxygen", "do"),
            unit="mg/L",
            unit_conversions={"mg/l": 1.0, "g/l": 1000.0, "ug/l": 0.001},
            minimum=0.0,
            maximum=25.0,
        ),
        FieldSpec(
            canonical="conductivity",
            label="电导率",
            aliases=("电导率", "conductivity", "ec"),
            unit="uS/cm",
            unit_conversions={"us/cm": 1.0, "ms/cm": 1000.0, "s/m": 10000.0},
            minimum=0.0,
            maximum=100000.0,
        ),
        FieldSpec(
            canonical="tp",
            label="总磷",
            aliases=("总磷", "tp", "total_phosphorus"),
            unit="mg/L",
            unit_conversions={"mg/l": 1.0, "ug/l": 0.001, "g/l": 1000.0},
            minimum=0.0,
            maximum=50.0,
        ),
        FieldSpec(
            canonical="tn",
            label="总氮",
            aliases=("总氮", "tn", "total_nitrogen"),
            unit="mg/L",
            unit_conversions={"mg/l": 1.0, "ug/l": 0.001, "g/l": 1000.0},
            minimum=0.0,
            maximum=200.0,
        ),
        FieldSpec(
            canonical="codmn",
            label="高锰酸盐指数",
            aliases=("高锰酸盐指数", "codmn", "cod_mn"),
            unit="mg/L",
            unit_conversions={"mg/l": 1.0, "ug/l": 0.001},
            minimum=0.0,
            maximum=100.0,
        ),
        FieldSpec(
            canonical="nh3_n",
            label="氨氮",
            aliases=("氨氮", "nh3_n", "nh3n", "ammonia_nitrogen"),
            unit="mg/L",
            unit_conversions={"mg/l": 1.0, "ug/l": 0.001},
            minimum=0.0,
            maximum=100.0,
        ),
        FieldSpec(
            canonical="secchi_depth_sd_m",
            label="透明度",
            aliases=("透明度", "secchi_depth_sd_m", "secchi_depth_m", "sd"),
            unit="m",
            unit_conversions={"m": 1.0, "cm": 0.01, "mm": 0.001},
            minimum=0.0,
            maximum=30.0,
        ),
        FieldSpec(
            canonical="water_quality_class",
            label="水质类别",
            aliases=("水质", "water_quality_class", "水质类别"),
            kind="categorical",
            aggregation="first",
        ),
        FieldSpec(
            canonical="station_name",
            label="站点名称",
            aliases=("站点名称", "station_name", "断面名称"),
            kind="categorical",
            aggregation="first",
        ),
        FieldSpec(
            canonical="river",
            label="河流",
            aliases=("河流", "river"),
            kind="categorical",
            aggregation="first",
        ),
    ),
    notes=(
        "原始文件第二行可能是单位行（如 (℃)、(mg/L)），解析时会被识别为单位而不是数据。",
    ),
)


# ---------------------------------------------------------------------------
# weather
# ---------------------------------------------------------------------------

WEATHER_SPEC = DatasetSpec(
    data_type="weather",
    label="气象观测",
    time_field=FieldSpec(
        canonical="date",
        label="日期",
        aliases=("date", "日期", "观测日期", "datetime"),
        kind="datetime",
        required=True,
    ),
    station_field=FieldSpec(
        canonical="station_code",
        label="气象站编码",
        aliases=("station_id_c", "站点编码", "station", "station_code"),
        kind="categorical",
        aggregation="first",
    ),
    fields=(
        FieldSpec(
            canonical="air_temp",
            label="平均气温",
            aliases=("平均气温", "air_temp", "temperature", "tem_avg"),
            unit="℃",
            unit_conversions={"°c": 1.0, "c": 1.0, "℃": 1.0},
            minimum=-40.0,
            maximum=55.0,
        ),
        FieldSpec(
            canonical="precipitation",
            label="当天降水量",
            aliases=("当天降水量", "降水量", "precipitation", "pre_time_2020", "rain"),
            unit="mm",
            unit_conversions={"mm": 1.0, "cm": 10.0, "m": 1000.0},
            minimum=0.0,
            maximum=1000.0,
            aggregation="sum",
        ),
        FieldSpec(
            canonical="humidity",
            label="相对湿度",
            aliases=("相对湿度", "humidity", "rhu"),
            unit="%",
            unit_conversions={"%": 1.0, "percent": 1.0, "1": 100.0},
            minimum=0.0,
            maximum=100.0,
        ),
        FieldSpec(
            canonical="wind_speed",
            label="平均风速",
            aliases=("平均风速", "wind_speed", "win_s_avg"),
            unit="m/s",
            unit_conversions={"m/s": 1.0, "km/h": 0.2777777778, "kn": 0.5144444444},
            minimum=0.0,
            maximum=80.0,
        ),
        FieldSpec(
            canonical="wind_direction",
            label="平均风向",
            aliases=("平均风向", "wind_direction", "win_d_avg"),
            unit="°",
            minimum=0.0,
            maximum=360.0,
        ),
        FieldSpec(
            canonical="pressure",
            label="气压",
            aliases=("气压", "pressure", "prs"),
            unit="hPa",
            unit_conversions={"hpa": 1.0, "kpa": 10.0, "pa": 0.01, "mbar": 1.0},
            minimum=800.0,
            maximum=1100.0,
        ),
    ),
    notes=(
        "气象文件常把日期拆成 Year / Mon / Day 三列，解析时会自动合成 date。",
    ),
)


# ---------------------------------------------------------------------------
# hydrodynamics
# ---------------------------------------------------------------------------

HYDRODYNAMICS_SPEC = DatasetSpec(
    data_type="hydrodynamics",
    label="水动力",
    time_field=DATE_FIELD,
    fields=(
        FieldSpec(
            canonical="huangdu_flow_m3s",
            label="黄渡流量",
            aliases=("huangdu_flow_m3s", "黄渡流量", "huangdu_discharge"),
            unit="m3/s",
            unit_conversions={"m3s": 1.0, "m3/s": 1.0, "l/s": 0.001},
            minimum=-10000.0,
            maximum=10000.0,
        ),
        FieldSpec(
            canonical="huangdu_water_level_m",
            label="黄渡水位",
            aliases=("huangdu_water_level_m", "黄渡水位"),
            unit="m",
            unit_conversions={"m": 1.0, "cm": 0.01},
            minimum=-10.0,
            maximum=30.0,
        ),
        FieldSpec(
            canonical="songpu_flow_m3s",
            label="松浦流量",
            aliases=("songpu_flow_m3s", "松浦流量", "songpu_discharge"),
            unit="m3/s",
            unit_conversions={"m3s": 1.0, "m3/s": 1.0, "l/s": 0.001},
            minimum=-10000.0,
            maximum=10000.0,
        ),
        FieldSpec(
            canonical="songpu_water_level_m",
            label="松浦水位",
            aliases=("songpu_water_level_m", "松浦水位"),
            unit="m",
            unit_conversions={"m": 1.0, "cm": 0.01},
            minimum=-10.0,
            maximum=30.0,
        ),
    ),
    preprocessor_required_markers=("逐日平均流量表", "月份", "测站编码："),
    preprocessor_hint=(
        "原始 shanghai_hydrodynamics.xls 是年块-月列-日行的透视报表，"
        "必须先经 scripts/preprocess 的水动力预处理生成 "
        "shanghai_hydrodynamics_daily_wide.csv 再接入。"
    ),
)


# ---------------------------------------------------------------------------
# boundary_labels
# ---------------------------------------------------------------------------

BOUNDARY_LABELS_SPEC = DatasetSpec(
    data_type="boundary_labels",
    label="边界标签",
    time_field=DATE_FIELD,
    fields=(
        FieldSpec(
            canonical="boundary_label",
            label="边界标签",
            aliases=("boundary_label", "边界标签"),
            minimum=0.0,
            maximum=1.0,
            required=True,
            aggregation="max",
        ),
        FieldSpec(
            canonical="boundary_extent_ratio",
            label="边界范围比例",
            aliases=("boundary_extent_ratio", "边界范围比例"),
            minimum=0.0,
            maximum=1.0,
        ),
        FieldSpec(
            canonical="label_confidence",
            label="标签置信度",
            aliases=("label_confidence", "置信度"),
            minimum=0.0,
            maximum=1.0,
        ),
        FieldSpec(
            canonical="water_fraction",
            label="水体占比",
            aliases=("water_fraction",),
            minimum=0.0,
            maximum=1.0,
        ),
        FieldSpec(
            canonical="edge_density",
            label="边缘密度",
            aliases=("edge_density",),
            minimum=0.0,
            maximum=1.0,
        ),
        FieldSpec(
            canonical="valid_fraction",
            label="有效像元占比",
            aliases=("valid_fraction",),
            minimum=0.0,
            maximum=1.0,
        ),
        FieldSpec(
            canonical="label_source",
            label="标签来源",
            aliases=("label_source",),
            kind="categorical",
            aggregation="first",
        ),
    ),
    notes=(
        "当前边界标签是 raster 派生代理标签，不是人工精标治理边界（见 AGENTS.md 事实边界）。",
    ),
)


# ---------------------------------------------------------------------------
# water_control
# ---------------------------------------------------------------------------

WATER_CONTROL_SPEC = DatasetSpec(
    data_type="water_control",
    label="水利调度",
    time_field=DATE_FIELD,
    station_field=STATION_FIELD,
    fields=(
        FieldSpec(
            canonical="gate_opening",
            label="闸门开度",
            aliases=("gate_opening", "闸门开度", "开度"),
            unit="m",
            unit_conversions={"m": 1.0, "cm": 0.01},
            minimum=0.0,
            maximum=50.0,
        ),
        FieldSpec(
            canonical="pump_flow_m3s",
            label="泵站流量",
            aliases=("pump_flow_m3s", "泵站流量"),
            unit="m3/s",
            unit_conversions={"m3s": 1.0, "m3/s": 1.0, "l/s": 0.001},
            minimum=-10000.0,
            maximum=10000.0,
        ),
        FieldSpec(
            canonical="operation_type",
            label="调度类型",
            aliases=("operation_type", "调度类型"),
            kind="categorical",
            aggregation="first",
        ),
    ),
)


# ---------------------------------------------------------------------------
# spatial
# ---------------------------------------------------------------------------

SPATIAL_SPEC = DatasetSpec(
    data_type="spatial",
    label="空间要素",
    time_field=DATE_FIELD,
    station_field=STATION_FIELD,
    granularity="static",
    fields=(
        FieldSpec(
            canonical="longitude",
            label="经度",
            aliases=("经度", "longitude", "lon", "lng"),
            unit="°",
            minimum=-180.0,
            maximum=180.0,
            aggregation="first",
        ),
        FieldSpec(
            canonical="latitude",
            label="纬度",
            aliases=("纬度", "latitude", "lat"),
            unit="°",
            minimum=-90.0,
            maximum=90.0,
            aggregation="first",
        ),
        FieldSpec(
            canonical="basin",
            label="流域",
            aliases=("流域", "basin"),
            kind="categorical",
            aggregation="first",
        ),
        FieldSpec(
            canonical="river",
            label="河流",
            aliases=("河流", "river"),
            kind="categorical",
            aggregation="first",
        ),
    ),
)


DATASET_SPECS: dict[str, DatasetSpec] = {
    spec.data_type: spec
    for spec in (
        WATER_QUALITY_SPEC,
        WEATHER_SPEC,
        HYDRODYNAMICS_SPEC,
        BOUNDARY_LABELS_SPEC,
        WATER_CONTROL_SPEC,
        SPATIAL_SPEC,
    )
}

SUPPORTED_DATA_TYPES: frozenset[str] = frozenset(DATASET_SPECS)

#: Data types the data-layer review (2026-08-28) asks us to register that are not
#: raw fact inputs to the modelling chain: station catalogs, proxy series, field
#: monitoring, cross-modal fusion tables and knowledge-graph relationships. They
#: are registered through ``DatasetService.register_derived_file`` (which computes
#: a quality report, field dictionary, lineage and hash without field mapping).
DERIVED_DATA_TYPES: frozenset[str] = frozenset(
    {
        "station_catalog",
        "proxy",
        "field_monitoring",
        "cross_modal",
        "knowledge_graph",
    }
)


def get_spec(data_type: str) -> DatasetSpec:
    try:
        return DATASET_SPECS[str(data_type).strip()]
    except KeyError as exc:
        raise ValueError(f"Unsupported data_type '{data_type}'.") from exc


def field_dictionary(data_type: str) -> dict[str, object]:
    """Machine-readable field dictionary for the data-asset centre (review item 8)."""
    spec = get_spec(data_type)
    return {
        "data_type": spec.data_type,
        "label": spec.label,
        "granularity": spec.granularity,
        "notes": list(spec.notes),
        "fields": [
            {
                "canonical": item.canonical,
                "label": item.label,
                "kind": item.kind,
                "unit": item.unit,
                "aliases": list(item.aliases),
                "accepted_units": sorted(item.unit_conversions),
                "minimum": item.minimum,
                "maximum": item.maximum,
                "required": item.required,
                "aggregation": item.aggregation,
            }
            for item in spec.all_fields
        ],
    }
