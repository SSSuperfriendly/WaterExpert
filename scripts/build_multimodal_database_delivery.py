from __future__ import annotations

import csv
import json
import math
import shutil
from pathlib import Path

import pandas as pd


ROOT = Path(r"G:\AI4S")
REPO_OUTPUTS = ROOT / "mscim_cmfbe_prototype" / "outputs"
DELIVERY_DIR = ROOT / "多模态水质综合数据库_20260412"
ZIP_PATH = ROOT / "多模态水质综合数据库_20260412.zip"


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def estimate_secchi_depth(ntu: float) -> float:
    if pd.isna(ntu) or ntu <= 0:
        return math.nan
    return 1.5 / (float(ntu) ** 0.7)


def add_secchi_column(df: pd.DataFrame, turbidity_col: str = "turbidity") -> pd.DataFrame:
    out = df.copy()
    out["secchi_depth_sd_m"] = out[turbidity_col].apply(estimate_secchi_depth)
    return out


def build_daily_water_quality() -> pd.DataFrame:
    source = ROOT / "上海市_宝山区_太湖流域_黄浦江_吴淞口_2586.csv"
    df = pd.read_csv(source)
    df["监测时间"] = pd.to_datetime(df["监测时间"], errors="coerce")
    df = df[df["监测时间"].notna()].copy()
    df["date"] = df["监测时间"].dt.date.astype(str)

    numeric_cols = [
        "经度",
        "纬度",
        "水温",
        "pH",
        "溶解氧",
        "电导率",
        "浊度",
        "高锰酸盐指数",
        "氨氮",
        "总有机碳",
        "总磷",
        "总氮",
        "叶绿素α",
        "藻密度",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    text_cols = [
        "省份",
        "城市",
        "流域",
        "河流",
        "站点名称",
        "水质",
        "站点",
    ]
    agg: dict[str, str] = {col: "first" for col in text_cols if col in df.columns}
    agg.update({col: "mean" for col in numeric_cols if col in df.columns})

    daily = df.groupby("date", as_index=False).agg(agg)
    daily = daily.rename(
        columns={
            "经度": "longitude",
            "纬度": "latitude",
            "水温": "water_temp",
            "pH": "ph",
            "溶解氧": "dissolved_oxygen",
            "电导率": "conductivity",
            "浊度": "turbidity",
            "高锰酸盐指数": "codmn",
            "氨氮": "nh3_n",
            "总有机碳": "toc",
            "总磷": "tp",
            "总氮": "tn",
            "叶绿素α": "chlorophyll_a",
            "藻密度": "algae_density",
            "省份": "province",
            "城市": "city",
            "流域": "basin",
            "河流": "river",
            "站点名称": "station_name",
            "水质": "water_quality_class",
            "站点": "station_status",
        }
    )
    daily = add_secchi_column(daily, "turbidity")
    daily["secchi_formula"] = "SD = 1.5 / NTU^0.7"
    return daily


def build_engineering_cases() -> pd.DataFrame:
    rows = [
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-01",
            "case_name": "奉贤区金海街道上海之鱼水系",
            "region": "上海市奉贤区",
            "waterbody_type": "湖-河复合水系",
            "key_measures": "水生森林净化技术；水生生物操纵技术；运维养护与轮捕轮放",
            "reported_effect": "透明度清澈见底或大于0.8 m；水质达到III类",
            "reported_transparency_m": ">=0.8",
            "reported_water_quality": "III类",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-02",
            "case_name": "青浦区徐泾镇蟠龙市河水系",
            "region": "上海市青浦区",
            "waterbody_type": "城市河道水系",
            "key_measures": "水生动植物生境修复；复合水生态系统构建；自动监测；数治平台智慧管控",
            "reported_effect": "透明度1.6-1.8 m；水质稳定III类",
            "reported_transparency_m": "1.6-1.8",
            "reported_water_quality": "III类",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-03",
            "case_name": "杨浦区新江湾城街道纬五河水系",
            "region": "上海市杨浦区",
            "waterbody_type": "景观河道",
            "key_measures": "复合水生植被系统；生态护岸；精准化专业养护",
            "reported_effect": "生态与景观提升；强调减少运动扰动与长期维护",
            "reported_transparency_m": "",
            "reported_water_quality": "",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-04",
            "case_name": "宝山区罗泾镇海星村水系",
            "region": "上海市宝山区",
            "waterbody_type": "河道水系",
            "key_measures": "水生境修复；水生态构建；水景观营造；数字赋能巡查",
            "reported_effect": "透明度可达1.5 m；主要水质指标稳定III类",
            "reported_transparency_m": "1.5",
            "reported_water_quality": "III类",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-05",
            "case_name": "金山区漕泾镇水库村水系",
            "region": "上海市金山区",
            "waterbody_type": "村级河道",
            "key_measures": "隐蔽式水下生态护岸；立体分层植物群落；疏拓河道与生态防汛融合",
            "reported_effect": "常年清澈见底；水质维持II-III类",
            "reported_transparency_m": "",
            "reported_water_quality": "II-III类",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-06",
            "case_name": "普陀区华东师范大学丽娃河水系",
            "region": "上海市普陀区",
            "waterbody_type": "校园河道",
            "key_measures": "截流控污；活水循环；底质改良；沉水植物恢复",
            "reported_effect": "能见度大于1.0 m；抑制藻类滋生；提升自净能力",
            "reported_transparency_m": ">1.0",
            "reported_water_quality": "",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-07",
            "case_name": "崇明区城桥镇新城湖水系",
            "region": "上海市崇明区",
            "waterbody_type": "湖泊",
            "key_measures": "污染控制净化；生态系统治理；循环系统和底部生物载体强化；长效管护",
            "reported_effect": "优良水质长久维持；生物多样性持续提升",
            "reported_transparency_m": "",
            "reported_water_quality": "优良",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-08",
            "case_name": "闵行区闵行文化公园水系",
            "region": "上海市闵行区",
            "waterbody_type": "公园水系",
            "key_measures": "生态缓冲带；水生生物操纵；水下森林净化；截污控污与长效管理",
            "reported_effect": "透明度达1.5 m；水质达到III类",
            "reported_transparency_m": "1.5",
            "reported_water_quality": "III类",
        },
        {
            "source_file": "上海清澈度提升典型案例（9例）(1).docx",
            "case_id": "SH-09",
            "case_name": "徐汇区虹梅街道上澳塘水系",
            "region": "上海市徐汇区",
            "waterbody_type": "城市河道",
            "key_measures": "生态护岸；整体绿化与海绵城市；微地形营造；人工增氧；生态浮床；水生动物恢复",
            "reported_effect": "改善水体清澈度与亲水体验；生态、防洪、景观多功能融合",
            "reported_transparency_m": "",
            "reported_water_quality": "",
        },
        {
            "source_file": "相关工程案例-中交(2).docx",
            "case_id": "EXT-01",
            "case_name": "嘉兴南湖水环境治理项目",
            "region": "浙江省嘉兴市",
            "waterbody_type": "城市湖泊",
            "key_measures": "净水降浊；环保清淤；湖区微地形改造；水生植物恢复",
            "reported_effect": "透明度提升至约1.0 m；悬浮物下降约80%；主要指标达III类",
            "reported_transparency_m": "1.0",
            "reported_water_quality": "III类",
        },
        {
            "source_file": "相关工程案例-中交(2).docx",
            "case_id": "EXT-02",
            "case_name": "嘉善祥符荡清水工程项目",
            "region": "浙江省嘉兴市嘉善县",
            "waterbody_type": "湖荡-联通河道系统",
            "key_measures": "清水降浊；生境改善；生态围隔；水生植物恢复；水生动物调控；监测平台",
            "reported_effect": "透明度总体平均2.0 m；水质稳定II类；沉水植物恢复188万平方米",
            "reported_transparency_m": "2.0",
            "reported_water_quality": "II类",
        },
        {
            "source_file": "相关工程案例-中交(2).docx",
            "case_id": "EXT-03",
            "case_name": "上海市典型河道生态治理（松江区九亭镇九科绿洲示范河道）",
            "region": "上海市松江区",
            "waterbody_type": "典型河道示范段",
            "key_measures": "物理过滤清水补给；生境改造与水质改善；水生态系统修复；长期监测与长效管理",
            "reported_effect": "透明度稳定0.8-1.0 m；总悬浮物降低65.7%；总磷降至0.1 mg/L以下",
            "reported_transparency_m": "0.8-1.0",
            "reported_water_quality": "III类",
        },
    ]
    return pd.DataFrame(rows)


def copy_sources(target_root: Path) -> list[dict[str, str]]:
    manifest: list[dict[str, str]] = []

    raw_dir = target_root / "00_原始来源"
    cases_dir = raw_dir / "工程案例"
    processed_dir = target_root / "01_预处理数据"
    docs_dir = target_root / "02_说明文档"

    for folder in [raw_dir, cases_dir, processed_dir, docs_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    source_files = [
        ROOT / "上海市_宝山区_太湖流域_黄浦江_吴淞口_2586.csv",
        ROOT / "daily_version_A_keep_missing.csv",
        ROOT / "上海水域环境发展有限公司资料提供.xls",
    ]
    for src in source_files:
        dst = raw_dir / src.name
        shutil.copy2(src, dst)
        manifest.append({"path": str(dst), "type": "raw_source"})

    for src in (ROOT / "工程案例").glob("*.docx"):
        dst = cases_dir / src.name
        shutil.copy2(src, dst)
        manifest.append({"path": str(dst), "type": "engineering_case_doc"})

    preprocessed_copy = [
        REPO_OUTPUTS / "hydrodynamics_preprocessed" / "shanghai_hydrodynamics_daily_long.csv",
        REPO_OUTPUTS / "hydrodynamics_preprocessed" / "shanghai_hydrodynamics_daily_wide.csv",
        REPO_OUTPUTS / "intermediate" / "multimodal_dataset_summary.json",
        REPO_OUTPUTS / "intermediate" / "multimodal_hydrodynamics_merge_summary.json",
        REPO_OUTPUTS / "hydrodynamics_preprocessed" / "summary.json",
    ]
    for src in preprocessed_copy:
        dst = processed_dir / src.name
        shutil.copy2(src, dst)
        manifest.append({"path": str(dst), "type": "preprocessed_copy"})

    return manifest


def write_readme(target_root: Path) -> None:
    docs_dir = target_root / "02_说明文档"
    readme = docs_dir / "README_数据库说明.md"
    content = """# 多模态水质综合数据库说明

## 1. 数据库目标

本目录用于交付一套可直接共享的多模态水质综合数据库，覆盖：

- 原始水质数据
- 气象数据
- 水动力数据
- 治理工程案例
- 预处理后的透明度换算数据
- 可直接用于多模态建模的融合数据

## 2. 透明度换算说明

本次新增透明度近似字段：

- `secchi_depth_sd_m`

换算公式为：

`SD = 1.5 / NTU^0.7`

其中：

- `SD` 为透明度 / Secchi depth 近似值，单位 m
- `NTU` 为浊度，单位 NTU

说明：

- 该字段是根据浊度经验公式换算得到的近似值
- 它可作为当前阶段的透明度 proxy
- 它不是现场实测 Secchi 深度

## 3. 当前最关键的数据表

- `water_quality_daily_with_secchi.csv`
  日尺度水质表，已加入透明度近似值
- `multimodal_daily_dataset_with_secchi.csv`
  多模态日尺度融合表，已加入透明度近似值
- `multimodal_daily_dataset_with_hydrodynamics_with_secchi.csv`
  融合水动力后的多模态日尺度表，已加入透明度近似值
- `治理工程案例索引.csv`
  从工程案例材料中整理出的可结构化案例索引

## 4. 口径提醒

- 当前有实测支撑的是：水质、气象、水动力站点数据、治理案例文本
- 当前属于机理代理项的是：潮汐滞留、床面剪切、再悬浮等过程量
- 当前透明度字段 `secchi_depth_sd_m` 为经验换算值，不是现场实测值
"""
    readme.write_text(content, encoding="utf-8")


def write_remote_sensing_note(target_root: Path) -> None:
    docs_dir = target_root / "02_说明文档"
    note = docs_dir / "外部可补充遥感产品线索_20260412.md"
    content = """# 外部可补充遥感产品线索

当前最适合后续补充的方向包括：

- 叶绿素 a / 藻类相关反演
- 水色与悬浮泥沙 / 浊度空间分布
- 光照 / PAR / Kd490 等辐射相关变量

说明：

- 这些产品可以优先作为空间增强数据源
- 对上海这种城市窄河道场景，直接套全球产品往往存在尺度和精度限制
- 更适合作为补充特征、背景场或先验信息，而不是直接当作最终真值
"""
    note.write_text(content, encoding="utf-8")


def write_manifest(target_root: Path, manifest_rows: list[dict[str, str]]) -> None:
    manifest_path = target_root / "02_说明文档" / "数据清单.csv"
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "type"])
        writer.writeheader()
        writer.writerows(manifest_rows)


def main() -> None:
    ensure_clean_dir(DELIVERY_DIR)

    manifest_rows = copy_sources(DELIVERY_DIR)

    processed_dir = DELIVERY_DIR / "01_预处理数据"

    water_daily = build_daily_water_quality()
    water_daily_path = processed_dir / "water_quality_daily_with_secchi.csv"
    water_daily.to_csv(water_daily_path, index=False, encoding="utf-8-sig")
    manifest_rows.append({"path": str(water_daily_path), "type": "derived_water_quality_daily"})

    multimodal = pd.read_csv(REPO_OUTPUTS / "intermediate" / "multimodal_daily_dataset.csv")
    multimodal = add_secchi_column(multimodal, "turbidity")
    multimodal["secchi_formula"] = "SD = 1.5 / NTU^0.7"
    multimodal_path = processed_dir / "multimodal_daily_dataset_with_secchi.csv"
    multimodal.to_csv(multimodal_path, index=False, encoding="utf-8-sig")
    manifest_rows.append({"path": str(multimodal_path), "type": "derived_multimodal_dataset"})

    multimodal_h = pd.read_csv(
        REPO_OUTPUTS / "intermediate" / "multimodal_daily_dataset_with_hydrodynamics.csv"
    )
    multimodal_h = add_secchi_column(multimodal_h, "turbidity")
    multimodal_h["secchi_formula"] = "SD = 1.5 / NTU^0.7"
    multimodal_h_path = processed_dir / "multimodal_daily_dataset_with_hydrodynamics_with_secchi.csv"
    multimodal_h.to_csv(multimodal_h_path, index=False, encoding="utf-8-sig")
    manifest_rows.append(
        {"path": str(multimodal_h_path), "type": "derived_multimodal_hydrodynamics_dataset"}
    )

    cases = build_engineering_cases()
    cases_path = processed_dir / "治理工程案例索引.csv"
    cases.to_csv(cases_path, index=False, encoding="utf-8-sig")
    manifest_rows.append({"path": str(cases_path), "type": "structured_engineering_cases"})

    write_readme(DELIVERY_DIR)
    write_remote_sensing_note(DELIVERY_DIR)
    manifest_rows.append(
        {"path": str(DELIVERY_DIR / "02_说明文档" / "README_数据库说明.md"), "type": "readme"}
    )
    manifest_rows.append(
        {
            "path": str(DELIVERY_DIR / "02_说明文档" / "外部可补充遥感产品线索_20260412.md"),
            "type": "note",
        }
    )

    summary = {
        "delivery_dir": str(DELIVERY_DIR),
        "zip_path": str(ZIP_PATH),
        "water_daily_rows": int(len(water_daily)),
        "multimodal_rows": int(len(multimodal)),
        "multimodal_with_hydrodynamics_rows": int(len(multimodal_h)),
        "engineering_case_rows": int(len(cases)),
        "secchi_formula": "SD = 1.5 / NTU^0.7",
    }
    summary_path = DELIVERY_DIR / "02_说明文档" / "交付摘要.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_rows.append({"path": str(summary_path), "type": "summary"})

    write_manifest(DELIVERY_DIR, manifest_rows)

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    shutil.make_archive(str(ZIP_PATH.with_suffix("")), "zip", DELIVERY_DIR)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
