"""Register the committed baseline files under ``data/`` as dataset versions.

The 2026-08-28 data-layer review found that the pre-existing research files in
``data/`` were never given a dataset/version identity: the pipeline and the query
service read them by fixed filename while new uploads go through ``DatasetService``.
This script closes that gap by driving every kept file through the same chain.

Two kinds of file are registered:

* **fact** files — raw inputs the model consumes (water quality, weather,
  hydrodynamics, boundary labels) — go through the full acceptance chain
  (``ingest_source_path``): field mapping, unit conversion, cleaning, time
  alignment, quality grading.
* **derived** files — station catalogs, proxy series, field-monitoring and
  cross-modal tables, knowledge-graph relationships — are already standardized
  fusion/reference tables, so they go through ``register_derived_file``, which
  still writes a canonical copy, a quality report, a field dictionary, lineage
  and a SHA-256 hash.

The script is idempotent: a file whose SHA-256 is already present as a version is
skipped, so re-running it never creates duplicate facts.

Usage::

    .ai4s/bin/python scripts/data/register_baseline_datasets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
# ``backend`` is a namespace package at the repo root (no __init__.py); the
# research library lives under src/water_ai. Mirror tests/conftest.py.
for root in (PROJECT_ROOT, SRC_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from backend.app.config import get_settings
from backend.app.services.dataset_service import DatasetService, sha256_file
from backend.app.services.state_store import SqliteStateStore

OWNER = "baseline-registration"

#: The 张家浜东闸站 proxy series: 三甲港 station 2198 supplies water quality and
#: 浦东 station 58370 supplies weather. The target site has no continuous local
#: series, so every page, task and report must show "代理数据".
ZHANGJIABANG_PROXY = {
    "target_site": "张家浜东闸站",
    "proxy_status": "substitute_not_direct_measurement",
    "water_quality_proxy_station_code": "2198",
    "water_quality_proxy_station_name": "三甲港",
    "water_quality_proxy_river": "川杨河",
    "weather_proxy_station_id": "58370",
    "weather_proxy_station_name": "浦东",
    "proxy_reason": (
        "张家浜东闸站无本地连续水质/气象监测，使用邻近三甲港站(2198)水质与"
        "浦东站(58370)气象作为代理。"
    ),
}

SECCHI_NOTE = [
    "透明度由浊度公式计算得到（SD = 1.5 / NTU^0.7），是代理值，不是直接测得的透明度。",
]

BOUNDARY_NOTE = [
    "边界标签是栅格派生的边界变化代理标签，不是人工精标治理边界。",
]

UAV_INCOMPLETE_NOTE = [
    "原始 UAV 媒体目录 data/raw/zhangjiabang_uav/ 缺失，仅有衍生特征，"
    "来源不完整、不可完全重建。",
]

KG_NOTE = [
    "知识图谱关系数据；原始文档缺失，不能完全重建。",
]

# Each entry names a dataset under a stable id, its data_type, and the committed
# source file. ``mode`` selects fact ingestion vs derived registration.
MANIFEST: list[dict[str, Any]] = [
    # --- fact sources (raw modelling inputs) --------------------------------
    {
        "dataset_id": "wq_wusongkou",
        "data_type": "water_quality",
        "station_code": "2586",
        "title": "吴淞口水质",
        "mode": "fact",
        "source_path": "data/raw/wusongkou_water_quality_2586.csv",
        "notes": ["主 pipeline 使用的吴淞口站(2586)水质原始文件。"],
    },
    {
        "dataset_id": "weather_shanghai",
        "data_type": "weather",
        "station_code": None,
        "title": "上海气象",
        "mode": "fact",
        "source_path": "data/raw/shanghai_weather_daily.csv",
        "notes": ["多气象站逐日数据，主 pipeline 与张家浜代理链路使用。"],
    },
    {
        "dataset_id": "hydro_shanghai",
        "data_type": "hydrodynamics",
        "station_code": None,
        "title": "上海水动力",
        "mode": "fact",
        "source_path": "outputs/hydrodynamics_preprocessed/shanghai_hydrodynamics_daily_wide.csv",
        "notes": [
            "黄渡/松浦流量与水位逐日宽表，由 data/raw/shanghai_hydrodynamics.xls 预处理而来。",
        ],
    },
    {
        "dataset_id": "boundary_wusongkou",
        "data_type": "boundary_labels",
        "station_code": "2586",
        "title": "吴淞口边界标签",
        "mode": "fact",
        "source_path": "data/raw/wusongkou_boundary_labels.csv",
        "notes": BOUNDARY_NOTE,
    },
    {
        "dataset_id": "wq_all_stations",
        "data_type": "water_quality",
        "station_code": None,
        "title": "全站水质",
        "mode": "fact",
        "source_path": "data/full_station_database/water_quality_daily_all_stations.csv",
        "notes": ["全站(20 站点)逐日水质加工表，是最重要的现有数据资产。"],
    },
    # --- derived / reference / proxy files ----------------------------------
    {
        "dataset_id": "station_catalog",
        "data_type": "station_catalog",
        "station_code": None,
        "title": "站点目录",
        "mode": "derived",
        "kind": "reference",
        "source_path": "data/full_station_database/station_catalog.csv",
        "notes": ["站点信息与覆盖范围，作为站点校验依据。"],
    },
    {
        "dataset_id": "wq_all_stations_secchi",
        "data_type": "water_quality",
        "station_code": None,
        "title": "全站水质（含透明度）",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/full_station_database/water_quality_daily_all_stations_with_secchi.csv",
        "notes": SECCHI_NOTE,
    },
    {
        "dataset_id": "wq_weather_fusion",
        "data_type": "cross_modal",
        "station_code": None,
        "title": "全站水质-天气融合宽表",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/full_station_database/multimodal_daily_all_stations_with_weather.csv",
        "notes": ["水质/透明度/天气融合结果，不得与原始水质气象并列作为可修改事实源。"],
    },
    {
        "dataset_id": "station_modality_summary",
        "data_type": "cross_modal",
        "station_code": None,
        "title": "全站模态覆盖摘要",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/full_station_database/multimodal_daily_all_stations_modality_summary.csv",
        "notes": ["各站模态覆盖统计，作为质量与覆盖摘要。"],
    },
    {
        "dataset_id": "station_weather_match",
        "data_type": "cross_modal",
        "station_code": None,
        "title": "水质站-气象站匹配结果",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/full_station_database/station_weather_match_summary.csv",
        "notes": ["水质站与气象站匹配结果与距离，记录匹配规则和生成时间。"],
    },
    {
        "dataset_id": "excluded_stations",
        "data_type": "station_catalog",
        "station_code": None,
        "title": "排除站点清单",
        "mode": "derived",
        "kind": "reference",
        "source_path": "data/full_station_database/excluded_station_files.csv",
        "notes": ["被排除站点及原因，作为站点质量记录。"],
    },
    {
        "dataset_id": "proxy_zhangjiabang",
        "data_type": "proxy",
        "station_code": "2198",
        "title": "张家浜代理数据",
        "mode": "derived",
        "kind": "proxy",
        "source_path": "data/proxy/zhangjiabang_proxy/zhangjiabang_proxy_daily.csv",
        "notes": ["张家浜东闸站代理数据，非实测数据。任何页面/任务/报告均须显示“代理数据”。"],
        "proxy": ZHANGJIABANG_PROXY,
    },
    {
        "dataset_id": "field_monitoring_zhangjiabang",
        "data_type": "field_monitoring",
        "station_code": None,
        "title": "张家浜现场监测",
        "mode": "derived",
        "kind": "fact_source",
        "source_path": "data/processed/zhangjiabang_cross_modal/field_monitoring_summary.csv",
        "notes": ["张家浜现场监测汇总（由 data/raw/zhangjiabang_field_monitoring.xlsx 解析）。"],
    },
    {
        "dataset_id": "field_monitoring_replicates",
        "data_type": "field_monitoring",
        "station_code": None,
        "title": "张家浜现场监测重复样",
        "mode": "derived",
        "kind": "fact_source",
        "source_path": "data/processed/zhangjiabang_cross_modal/field_monitoring_replicates.csv",
        "notes": ["现场监测重复样明细。"],
    },
    {
        "dataset_id": "uav_asset_index",
        "data_type": "cross_modal",
        "station_code": None,
        "title": "UAV 资产索引",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/processed/zhangjiabang_cross_modal/uav_asset_index.csv",
        "notes": UAV_INCOMPLETE_NOTE,
    },
    {
        "dataset_id": "uav_visual_daily",
        "data_type": "cross_modal",
        "station_code": None,
        "title": "UAV 视觉逐日特征",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/processed/zhangjiabang_cross_modal/uav_visual_daily_features.csv",
        "notes": UAV_INCOMPLETE_NOTE,
    },
    {
        "dataset_id": "cross_modal_zhangjiabang",
        "data_type": "cross_modal",
        "station_code": None,
        "title": "张家浜跨模态融合日表",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/processed/zhangjiabang_cross_modal/zhangjiabang_cross_modal_daily.csv",
        "notes": ["现场监测 + UAV 视觉特征 + 代理气象对齐后的跨模态日表。"],
    },
    {
        "dataset_id": "kg_relationships",
        "data_type": "knowledge_graph",
        "station_code": None,
        "title": "知识图谱关系",
        "mode": "derived",
        "kind": "derived",
        "source_path": "data/knowledge_graph/create_final_relationships.parquet",
        "notes": KG_NOTE,
    },
]


def main() -> None:
    settings = get_settings()
    store = SqliteStateStore(settings.state_root)
    service = DatasetService(settings, store)

    registered: list[dict[str, Any]] = []
    skipped: list[str] = []
    for entry in MANIFEST:
        source = PROJECT_ROOT / entry["source_path"]
        if not source.is_file():
            print(f"[skip] missing source: {entry['source_path']}")
            continue

        dataset_id = str(entry["dataset_id"])
        service.ensure_dataset(
            dataset_id=dataset_id,
            data_type=str(entry["data_type"]),
            station_code=entry.get("station_code"),
            owner=OWNER,
            title=entry.get("title"),
            kind=entry.get("kind", "fact_source"),
            notes=entry.get("notes"),
            proxy=entry.get("proxy"),
        )

        digest = sha256_file(source)
        if service.has_version_with_sha(dataset_id, digest):
            skipped.append(dataset_id)
            continue

        kwargs: dict[str, Any] = dict(
            source_path=source,
            data_type=str(entry["data_type"]),
            station_code=entry.get("station_code"),
            owner=OWNER,
            dataset_id=dataset_id,
            title=entry.get("title"),
            notes=entry.get("notes"),
            proxy=entry.get("proxy"),
        )
        if entry.get("mode") == "fact":
            record = service.ingest_source_path(**kwargs)
        else:
            record = service.register_derived_file(**kwargs)

        registered.append(
            {
                "dataset_id": dataset_id,
                "version_id": record["version_id"],
                "data_type": entry["data_type"],
                "source_path": entry["source_path"],
                "status": record["status"],
                "quality_grade": record["quality_grade"],
                "modelable": record["modelable"],
                "coverage_start": record.get("coverage_start"),
                "coverage_end": record.get("coverage_end"),
                "rows": record.get("aligned_rows") or record.get("source_rows"),
                "kind": record.get("kind", "fact_source"),
            }
        )
        print(
            f"[ok] {dataset_id:<26} {record['version_id']:<20} "
            f"{record['status']:<9} grade={record['quality_grade']} "
            f"rows={record.get('aligned_rows') or record.get('source_rows')}"
        )

    if skipped:
        print(f"[skip] already registered (unchanged): {', '.join(skipped)}")

    print(
        f"\nRegistered {len(registered)} version(s) into {settings.datasets_root}; "
        f"skipped {len(skipped)} unchanged."
    )
    if registered:
        print(json.dumps(registered, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
