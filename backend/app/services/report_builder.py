from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.app.schemas import ReportExportFormat
from backend.app.services.artifact_repository import ArtifactRepository


REPORT_MEDIA_TYPES: dict[ReportExportFormat, str] = {
    "html": "text/html; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
    "pdf": "application/pdf",
}

REPORT_FILE_SUFFIXES: dict[ReportExportFormat, str] = {
    "html": ".html",
    "md": ".md",
    "json": ".json",
    "pdf": ".pdf",
}

REPORT_FILENAME_PREFIX = "waterexpert-software-report"
REPORT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S-%f"
REPORT_ID_LENGTH = 8
REPORT_TITLE = "WaterExpert 水环境智能诊断报告"
REPORT_INTRO = (
    "本报告汇总当前 WaterExpert 软件中吴淞口单站点、多模态、日尺度原型结果，"
    "用于预测复核、诊断研判与报告留存，不用于自动控制或治理决策替代。"
)
REPORT_EMPTY_TEXT = "暂无数据。"
PDF_FONT_NAME = "STSong-Light"
PDF_BODY_FONT_SIZE = 8
PDF_HEADER_FONT_SIZE = 8
PDF_CELL_PADDING = 4
PDF_TABLE_WIDTH_WEIGHTS: dict[str, list[float]] = {
    "priority_rows": [1.2, 1.1, 0.8, 0.9, 2.8],
    "prediction_rows": [1.1, 0.95, 0.95, 0.95, 0.95, 1.1],
    "driver_rows": [1.2, 1.5, 0.8],
    "process_rows": [1.2, 0.8, 1.0, 0.8, 0.8],
    "threshold_rows": [1.3, 0.75, 0.8, 0.75, 0.8, 0.85],
    "boundary_rows": [1.0, 1.0, 1.0, 0.9, 0.9],
    "sobol_rows": [1.4, 0.9, 0.9, 0.9],
}

PROTOTYPE_SCOPE_LABELS = {
    "single-station multimodal daily prototype": "单站点多模态日尺度原型",
}
SCENARIO_LABELS = {
    "external_input": "外源输入",
    "internal_release": "内源释放",
    "algal_dominant": "藻类主导",
    "chronic_composite": "慢性复合",
}
RISK_BAND_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}
DIRECTION_LABELS = {
    "source": "来源",
    "sink": "汇",
    "driver": "驱动",
    "inhibitor": "抑制",
}
STATUS_LABELS = {
    "ok": "正常",
    "watch": "关注",
    "insufficient": "证据不足",
}
UNIT_LABELS = {
    "dimensionless": "无量纲",
    "degC": "摄氏度",
    "m/s": "米/秒",
    "m3/s": "立方米/秒",
    "proxy": "代理指标",
}
FEATURE_LABELS = {
    "Hydrodynamic velocity proxy": "水动力速度代理",
    "Bed shear proxy": "床面切应力代理",
    "3-day cumulative precipitation": "3日累计降雨",
    "7-day cumulative precipitation": "7日累计降雨",
    "Wind speed": "风速",
    "Air temperature": "气温",
    "Songpu absolute flow": "松浦绝对流量",
    "Huangdu absolute flow": "黄渡绝对流量",
    "Songpu tidal pumping proxy": "松浦潮汐泵送代理",
    "Songpu resuspension potential": "松浦再悬浮潜力",
    "Songpu flushing potential": "松浦冲刷潜力",
    "runoff sediment pulse": "径流泥沙脉冲",
    "dissolved oxygen": "溶解氧",
    "self-purification index": "自净指数",
    "water temperature": "水温",
}
TEXT_TRANSLATIONS = {
    "Current outputs support empirical diagnosis and screening, not calibrated operational control.": "当前产物仅支持经验性诊断与筛查，不代表经过标定的运行控制依据。",
    "Do not claim a full multi-station hydrodynamic model has been trained.": "不要将当前系统表述为已完成全域多站点水动力模型训练。",
    "Do not claim calibrated spatial governance maps or validated control policies are available.": "不要将当前产物表述为已提供经过校准的空间治理图或验证后的控制策略。",
    "Thresholds denote empirical critical levels at which turbidity forcing tends to exceed self-purification capacity or turbidity tends to increase sharply in the current prototype.": "阈值表示当前原型下，致浊作用开始明显超过自净能力或浊度出现跃升的经验临界水平。",
    "The current scenario layer is a deterministic empirical triage built from CMFBE process outputs, auxiliary risk scores, and exported threshold breakpoints.": "当前场景层是基于 CMFBE 过程输出、辅助风险分数和导出阈值断点构建的确定性经验分诊结果。",
    "Scenario labels describe empirical forcing regimes under which turbidity transport and self-purification balance appear to shift in the current prototype.": "场景标签描述的是当前原型中浊度输运与自净平衡出现转变时对应的经验驱动状态。",
}
SCENARIO_GUARDRAILS = [
    "场景标签来自经验型 triage 产物，不是经过验证的治理分类标准。",
    "阈值检索展示的是当前原型中的经验断点，不是二维水动力物理控制阈值。",
    "响应建议用于辅助分析师排查与监测优先级判断，不代表自动控制策略。",
]
EVIDENCE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("3-day precipitation exceeded threshold", "3日累计降雨超过阈值"),
    ("7-day precipitation exceeded threshold", "7日累计降雨超过阈值"),
    ("air temperature exceeded warm threshold", "气温超过偏暖阈值"),
    ("bed shear proxy exceeded threshold", "床面切应力代理超过阈值"),
    ("resuspension potential exceeded empirical threshold", "再悬浮潜力超过经验阈值"),
    ("flushing potential remained below empirical threshold", "冲刷潜力低于经验阈值"),
    ("flushing potential was strong", "冲刷潜力较强"),
    ("runoff sediment pulse exceeded empirical threshold", "径流泥沙脉冲超过经验阈值"),
)


@dataclass(frozen=True)
class ReportTableSection:
    title: str
    payload_key: str
    columns: list[tuple[str, str]]


TABLE_SECTIONS: tuple[ReportTableSection, ...] = (
    ReportTableSection(
        title="高优先级事件",
        payload_key="priority_rows",
        columns=[
            ("target_date", "日期"),
            ("primary_scenario", "场景"),
            ("risk_band", "风险"),
            ("predicted_critical_transition_prob", "转折概率"),
            ("evidence_summary", "证据摘要"),
        ],
    ),
    ReportTableSection(
        title="预测预览",
        payload_key="prediction_rows",
        columns=[
            ("target_date", "日期"),
            ("actual_turbidity", "实测浊度"),
            ("predicted_turbidity", "预测浊度"),
            ("actual_clearness", "实测清澈度"),
            ("predicted_clearness", "预测清澈度"),
            ("predicted_critical_transition_prob", "转折概率"),
        ],
    ),
    ReportTableSection(
        title="主导因子诊断",
        payload_key="driver_rows",
        columns=[
            ("feature", "特征"),
            ("feature_label", "名称"),
            ("driver_score", "驱动分数"),
        ],
    ),
    ReportTableSection(
        title="过程分解",
        payload_key="process_rows",
        columns=[
            ("process_label", "过程"),
            ("direction", "方向"),
            ("mean_contribution", "平均贡献"),
            ("std_contribution", "波动"),
            ("max_contribution", "峰值"),
        ],
    ),
)

TRAILING_TABLE_SECTIONS: tuple[ReportTableSection, ...] = (
    ReportTableSection(
        title="边界识别摘要",
        payload_key="boundary_rows",
        columns=[
            ("cmfbe_test_f1", "CMFBE F1"),
            ("cmfbe_test_accuracy", "CMFBE 准确率"),
            ("mscim_test_f1", "MSCIM F1"),
            ("overall_positive_rate", "正样本率"),
            ("labeled_samples", "标注样本"),
        ],
    ),
    ReportTableSection(
        title="敏感性摘要",
        payload_key="sobol_rows",
        columns=[
            ("factor_label", "因子"),
            ("first_order_index", "一阶"),
            ("total_order_index", "总效应"),
            ("interaction_strength", "交互"),
        ],
    ),
)

THRESHOLD_COLUMNS = [
    ("feature_label", "特征"),
    ("threshold", "阈值"),
    ("unit", "单位"),
    ("r2_gain", "R²增益"),
    ("response_jump", "响应跃变"),
    ("status", "状态"),
]


def _get_nested(mapping: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_text(value: Any) -> str:
    return "" if value is None else str(value)


def _translate_text(value: Any) -> str:
    text = _normalize_text(value)
    return TEXT_TRANSLATIONS.get(text, text)


def _translate_feature_label(label: Any) -> str:
    text = _normalize_text(label)
    return FEATURE_LABELS.get(text, text)


def _translate_scenario(value: Any) -> str:
    text = _normalize_text(value)
    return SCENARIO_LABELS.get(text, text)


def _translate_risk_band(value: Any) -> str:
    text = _normalize_text(value)
    return RISK_BAND_LABELS.get(text, text)


def _translate_direction(value: Any) -> str:
    text = _normalize_text(value)
    return DIRECTION_LABELS.get(text, text)


def _translate_status(value: Any) -> str:
    text = _normalize_text(value)
    return STATUS_LABELS.get(text, text)


def _translate_unit(value: Any) -> str:
    text = _normalize_text(value)
    return UNIT_LABELS.get(text, text)


def _translate_guardrails(items: list[Any]) -> list[str]:
    return [_translate_text(item) for item in items if _normalize_text(item)]


def _translate_evidence_summary(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    translated = text.replace("; ", "；")
    for source, target in EVIDENCE_REPLACEMENTS:
        translated = translated.replace(source, target)
    return translated.replace("degC", "摄氏度")


def _format_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    text = str(value)
    if "T" in text and text.endswith(".000"):
        return text.split("T", maxsplit=1)[0]
    return text


def _copy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _localize_priority_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    localized = _copy_rows(rows)
    for row in localized:
        row["primary_scenario"] = _translate_scenario(row.get("primary_scenario"))
        row["risk_band"] = _translate_risk_band(row.get("risk_band"))
        row["evidence_summary"] = _translate_evidence_summary(row.get("evidence_summary"))
    return localized


def _localize_prediction_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _copy_rows(rows)


def _localize_driver_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    localized = _copy_rows(rows)
    for row in localized:
        row["feature_label"] = _translate_feature_label(row.get("feature_label"))
    return localized


def _localize_process_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    localized = _copy_rows(rows)
    for row in localized:
        row["process_label"] = _translate_feature_label(row.get("process_label"))
        row["direction"] = _translate_direction(row.get("direction"))
    return localized


def _localize_threshold_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    localized = _copy_rows(rows)
    for row in localized:
        row["feature_label"] = _translate_feature_label(row.get("feature_label"))
        row["unit"] = _translate_unit(row.get("unit"))
        row["status"] = _translate_status(row.get("status"))
    return localized


def _localize_sobol_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    localized = _copy_rows(rows)
    for row in localized:
        row["factor_label"] = _translate_feature_label(row.get("factor_label"))
    return localized


def _card_list(items: list[str]) -> str:
    return "".join(f"<li>{escape(str(item))}</li>" for item in items)


def _table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return f"<p class='empty'>{REPORT_EMPTY_TEXT}</p>"
    header = "".join(f"<th>{escape(label)}</th>" for _, label in columns)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{escape(_format_scalar(row.get(key)))}</td>"
            for key, _ in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return f"_{REPORT_EMPTY_TEXT}_"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| "
        + " | ".join(_format_scalar(row.get(key)) for key, _ in columns)
        + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body])


def _metric_chips(metrics: dict[str, Any]) -> str:
    return "".join(
        f"<li>{escape(label)}: {escape(_format_scalar(value))}</li>" for label, value in metrics.items()
    )


def _markdown_bullets(items: list[str]) -> str:
    if not items:
        return "- 暂无"
    return "\n".join(f"- {item}" for item in items)


def _pdf_table(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    *,
    table_key: str,
    max_width: float,
    styles: dict[str, ParagraphStyle],
) -> Table:
    data = [[Paragraph(label, styles["TableHeader"]) for _, label in columns]]
    if rows:
        for row in rows:
            data.append(
                [
                    Paragraph(escape(_format_scalar(row.get(key))), styles["TableBody"])
                    for key, _ in columns
                ]
            )
    else:
        data.append(
            [Paragraph(REPORT_EMPTY_TEXT, styles["TableBody"])]
            + [Paragraph("", styles["TableBody"]) for _ in range(len(columns) - 1)]
        )

    weights = PDF_TABLE_WIDTH_WEIGHTS.get(table_key, [1] * len(columns))
    total_weight = sum(weights) or len(columns)
    col_widths = [(max_width * weight) / total_weight for weight in weights]
    table = LongTable(data, colWidths=col_widths, repeatRows=1, splitByRow=True)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2efe6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#122033")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d3c2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), PDF_FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), PDF_BODY_FONT_SIZE),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), PDF_CELL_PADDING),
                ("RIGHTPADDING", (0, 0), (-1, -1), PDF_CELL_PADDING),
                ("TOPPADDING", (0, 0), (-1, -1), PDF_CELL_PADDING),
                ("BOTTOMPADDING", (0, 0), (-1, -1), PDF_CELL_PADDING),
            ]
        )
    )
    return table


def _pdf_section_heading(styles: dict[str, ParagraphStyle], title: str) -> Paragraph:
    return Paragraph(title, styles["Heading2"])


def _pdf_body(styles: dict[str, ParagraphStyle], text: str) -> Paragraph:
    sanitized = escape(text).replace("&lt;br/&gt;", "<br/>").replace("\n", "<br/>")
    return Paragraph(sanitized, styles["BodyText"])


def _collect_report_payload(repository: ArtifactRepository) -> dict[str, Any]:
    dashboard = repository.dashboard()
    predictions = repository.predictions(model=None, split="test")
    diagnostics = repository.diagnostics()
    triage = repository.scenario_triage()
    thresholds = repository.thresholds(feature=None)
    boundary = repository.boundary()
    sensitivity = repository.sensitivity()

    selected_model = _normalize_text(predictions.get("selected_model"))
    selected_metrics = _dict_value(dashboard.get("test_models")).get(selected_model, {})
    boundary_summary = _dict_value(boundary.get("summary"))
    boundary_overall = _dict_value(_get_nested(boundary_summary, "overall", "test", default={}))
    diagnostics_summary = _dict_value(diagnostics.get("factor_summary"))
    sobol = _dict_value(sensitivity.get("sobol"))

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dashboard": {
            **dashboard,
            "prototype_scope": PROTOTYPE_SCOPE_LABELS.get(
                _normalize_text(dashboard.get("prototype_scope")),
                _normalize_text(dashboard.get("prototype_scope")),
            ),
            "guardrails": _translate_guardrails(_list_value(dashboard.get("guardrails"))),
        },
        "predictions": predictions,
        "diagnostics": diagnostics,
        "triage": {
            **triage,
            "classification_semantics": _translate_text(triage.get("classification_semantics")),
            "threshold_semantics": _translate_text(triage.get("threshold_semantics")),
        },
        "thresholds": {
            **thresholds,
            "threshold_semantics": _translate_text(thresholds.get("threshold_semantics")),
        },
        "boundary": boundary,
        "sensitivity": sensitivity,
        "selected_model": selected_model,
        "selected_metrics": {
            "浊度 R²": selected_metrics.get("turbidity_r2"),
            "浊度 RMSE": selected_metrics.get("turbidity_rmse"),
            "清澈度 R²": selected_metrics.get("clearness_r2"),
            "清澈度 RMSE": selected_metrics.get("clearness_rmse"),
        },
        "priority_rows": _localize_priority_rows(_list_value(dashboard.get("high_priority_days"))[:10]),
        "prediction_rows": _localize_prediction_rows(_list_value(predictions.get("series"))[:12]),
        "driver_rows": _localize_driver_rows(_list_value(diagnostics_summary.get("top_driver_features"))[:8]),
        "process_rows": _localize_process_rows(_list_value(diagnostics.get("process_decomposition"))[:7]),
        "threshold_rows": _localize_threshold_rows(_list_value(thresholds.get("summary"))[:12]),
        "sobol_rows": _localize_sobol_rows(_list_value(sobol.get("top_factors"))[:8]),
        "boundary_rows": [
            {
                "cmfbe_test_f1": _get_nested(boundary_summary, "models", "cmfbe_stgcn", "test", "f1"),
                "cmfbe_test_accuracy": _get_nested(
                    boundary_summary,
                    "models",
                    "cmfbe_stgcn",
                    "test",
                    "accuracy",
                ),
                "mscim_test_f1": _get_nested(boundary_summary, "models", "mscim", "test", "f1"),
                "overall_positive_rate": boundary_overall.get("positive_rate"),
                "labeled_samples": boundary_overall.get("labeled_samples"),
            }
        ],
        "scenario_guardrails": SCENARIO_GUARDRAILS,
    }


def _html_table_sections(payload: dict[str, Any]) -> str:
    return "".join(
        f"""
    <h2>{escape(section.title)}</h2>
    <div class="panel">
      {_table(_list_value(payload.get(section.payload_key)), section.columns)}
    </div>
"""
        for section in TABLE_SECTIONS
    )


def _html_trailing_table_sections(payload: dict[str, Any]) -> str:
    return "".join(
        f"""
    <h2>{escape(section.title)}</h2>
    <div class="panel">
      {_table(_list_value(payload.get(section.payload_key)), section.columns)}
    </div>
"""
        for section in TRAILING_TABLE_SECTIONS
    )


def _markdown_table_sections(payload: dict[str, Any]) -> list[str]:
    sections: list[str] = []
    for section in TABLE_SECTIONS:
        sections.extend(
            [
                f"## {section.title}",
                "",
                _markdown_table(_list_value(payload.get(section.payload_key)), section.columns),
                "",
            ]
        )
    return sections


def _markdown_trailing_table_sections(payload: dict[str, Any]) -> list[str]:
    sections: list[str] = []
    for section in TRAILING_TABLE_SECTIONS:
        sections.extend(
            [
                f"## {section.title}",
                "",
                _markdown_table(_list_value(payload.get(section.payload_key)), section.columns),
                "",
            ]
        )
    return sections


def _pdf_table_sections(
    payload: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    max_width: float,
) -> list[Any]:
    story: list[Any] = []
    for section in TABLE_SECTIONS:
        story.extend(
            [
                _pdf_section_heading(styles, section.title),
                _pdf_table(
                    _list_value(payload.get(section.payload_key)),
                    section.columns,
                    table_key=section.payload_key,
                    max_width=max_width,
                    styles=styles,
                ),
            ]
        )
    return story


def _pdf_trailing_table_sections(
    payload: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    max_width: float,
) -> list[Any]:
    story: list[Any] = []
    for section in TRAILING_TABLE_SECTIONS:
        story.extend(
            [
                _pdf_section_heading(styles, section.title),
                _pdf_table(
                    _list_value(payload.get(section.payload_key)),
                    section.columns,
                    table_key=section.payload_key,
                    max_width=max_width,
                    styles=styles,
                ),
            ]
        )
    return story


def build_report_html(repository: ArtifactRepository) -> str:
    payload = _collect_report_payload(repository)
    dashboard = payload["dashboard"]
    triage = payload["triage"]
    thresholds = payload["thresholds"]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{REPORT_TITLE}</title>
  <style>
    :root {{
      --ink: #122033;
      --muted: #4d6278;
      --paper: #f6f4ed;
      --panel: #fffdf8;
      --line: #d9d3c2;
      --accent: #0f766e;
      --accent-2: #d97706;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #eef6f6 0%, var(--paper) 38%, #f9f7f2 100%);
      color: var(--ink);
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 40px 28px 60px;
    }}
    h1, h2, h3 {{
      font-family: "Palatino Linotype", "Book Antiqua", serif;
      margin: 0 0 12px;
    }}
    h1 {{
      font-size: 40px;
      line-height: 1;
    }}
    h2 {{
      margin-top: 30px;
      font-size: 24px;
      border-top: 1px solid var(--line);
      padding-top: 24px;
    }}
    p, li {{
      color: var(--muted);
      line-height: 1.6;
    }}
    .hero {{
      display: grid;
      gap: 18px;
      grid-template-columns: 1.5fr 1fr;
      align-items: start;
    }}
    .panel {{
      background: rgba(255, 253, 248, 0.9);
      border: 1px solid rgba(217, 211, 194, 0.9);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 18px 40px rgba(18, 32, 51, 0.08);
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 0;
      list-style: none;
      margin: 0;
    }}
    .chips li {{
      color: var(--ink);
      background: #eef6f4;
      border: 1px solid #cde0db;
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 13px;
    }}
    .warning {{
      border-left: 4px solid var(--accent-2);
      padding-left: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      background: var(--panel);
    }}
    th, td {{
      border-bottom: 1px solid #ece7db;
      text-align: left;
      padding: 10px 8px;
      vertical-align: top;
    }}
    th {{
      color: var(--ink);
      background: #f2efe6;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 18px;
    }}
    .meta strong {{
      display: block;
      color: var(--ink);
    }}
    .empty {{
      font-style: italic;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="panel">
        <h1>{REPORT_TITLE}</h1>
        <p>{REPORT_INTRO}</p>
        <div class="meta">
          <div><strong>站点</strong>{escape(_normalize_text(dashboard["station_profile"]["station_name"]))}</div>
          <div><strong>河流</strong>{escape(_normalize_text(dashboard["station_profile"]["river"]))}</div>
          <div><strong>范围</strong>{escape(_normalize_text(dashboard["prototype_scope"]))}</div>
          <div><strong>建模匹配日数</strong>{escape(_format_scalar(dashboard["station_profile"]["matched_model_rows"]))}</div>
        </div>
      </div>
      <div class="panel warning">
        <h3>边界说明</h3>
        <ul>{_card_list(dashboard["guardrails"])}</ul>
      </div>
    </section>

    <h2>模型概览</h2>
    <div class="panel">
      <p>当前主模型：<strong>{escape(payload["selected_model"])}</strong></p>
      <ul class="chips">{_metric_chips(payload["selected_metrics"])}</ul>
    </div>

    {_html_table_sections(payload)}

    <h2>阈值检索</h2>
    <div class="panel">
      <p>{escape(_normalize_text(thresholds.get("threshold_semantics", "")))}</p>
      {_table(payload["threshold_rows"], THRESHOLD_COLUMNS)}
    </div>

    {_html_trailing_table_sections(payload)}

    <h2>场景边界说明</h2>
    <div class="panel">
      <p>{escape(_normalize_text(triage.get("classification_semantics", "")))}</p>
      <ul>{_card_list(payload["scenario_guardrails"])}</ul>
    </div>

    <p>生成时间：{escape(payload["generated_at"])}</p>
  </main>
</body>
</html>"""


def build_report_markdown(repository: ArtifactRepository) -> str:
    payload = _collect_report_payload(repository)
    dashboard = payload["dashboard"]
    thresholds = payload["thresholds"]
    triage = payload["triage"]

    lines = [
        f"# {REPORT_TITLE}",
        "",
        REPORT_INTRO,
        "",
        "## 概览",
        "",
        f"- 站点：{dashboard['station_profile']['station_name']}",
        f"- 河流：{dashboard['station_profile']['river']}",
        f"- 范围：{dashboard['prototype_scope']}",
        f"- 建模匹配日数：{dashboard['station_profile']['matched_model_rows']}",
        f"- 当前主模型：{payload['selected_model']}",
        "",
        "## 边界说明",
        "",
        _markdown_bullets(dashboard["guardrails"]),
        "",
        "## 模型指标",
        "",
        _markdown_bullets(
            [f"{label}: {_format_scalar(value)}" for label, value in payload["selected_metrics"].items()]
        ),
        "",
        *_markdown_table_sections(payload),
        "## 阈值检索",
        "",
        _normalize_text(thresholds.get("threshold_semantics", "")),
        "",
        _markdown_table(payload["threshold_rows"], THRESHOLD_COLUMNS),
        "",
        *_markdown_trailing_table_sections(payload),
        "## 场景边界说明",
        "",
        _normalize_text(triage.get("classification_semantics", "")),
        "",
        _markdown_bullets(payload["scenario_guardrails"]),
        "",
        f"生成时间：{payload['generated_at']}",
    ]
    return "\n".join(lines)


def build_report_json(repository: ArtifactRepository) -> str:
    return json.dumps(_collect_report_payload(repository), ensure_ascii=False, indent=2)


def build_report_pdf(repository: ArtifactRepository) -> bytes:
    payload = _collect_report_payload(repository)
    dashboard = payload["dashboard"]
    thresholds = payload["thresholds"]
    triage = payload["triage"]

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=REPORT_TITLE,
    )

    registerFont(UnicodeCIDFont(PDF_FONT_NAME))
    stylesheet = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {
        "Title": ParagraphStyle(
            "WaterExpertTitle",
            parent=stylesheet["Title"],
            fontName=PDF_FONT_NAME,
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#122033"),
            spaceAfter=10,
        ),
        "Heading2": ParagraphStyle(
            "WaterExpertHeading2",
            parent=stylesheet["Heading2"],
            fontName=PDF_FONT_NAME,
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#122033"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "BodyText": ParagraphStyle(
            "WaterExpertBody",
            parent=stylesheet["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#4d6278"),
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "TableHeader": ParagraphStyle(
            "WaterExpertTableHeader",
            parent=stylesheet["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=PDF_HEADER_FONT_SIZE,
            leading=10,
            textColor=colors.HexColor("#122033"),
            wordWrap="CJK",
        ),
        "TableBody": ParagraphStyle(
            "WaterExpertTableBody",
            parent=stylesheet["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=PDF_BODY_FONT_SIZE,
            leading=10,
            textColor=colors.HexColor("#4d6278"),
            wordWrap="CJK",
        ),
    }
    max_table_width = document.width

    story = [
        Paragraph(REPORT_TITLE, styles["Title"]),
        _pdf_body(styles, REPORT_INTRO),
        Spacer(1, 4),
        _pdf_body(styles, f"站点：{dashboard['station_profile']['station_name']}"),
        _pdf_body(styles, f"河流：{dashboard['station_profile']['river']}"),
        _pdf_body(styles, f"范围：{dashboard['prototype_scope']}"),
        _pdf_body(styles, f"建模匹配日数：{dashboard['station_profile']['matched_model_rows']}"),
        Spacer(1, 6),
        _pdf_section_heading(styles, "边界说明"),
        _pdf_body(styles, "<br/>".join(dashboard["guardrails"])),
        _pdf_section_heading(styles, "模型概览"),
        _pdf_body(styles, f"当前主模型：{payload['selected_model']}"),
        _pdf_body(
            styles,
            " | ".join(f"{label}: {_format_scalar(value)}" for label, value in payload["selected_metrics"].items()),
        ),
        *_pdf_table_sections(payload, styles, max_table_width),
        _pdf_section_heading(styles, "阈值检索"),
        _pdf_body(styles, _normalize_text(thresholds.get("threshold_semantics", ""))),
        _pdf_table(
            payload["threshold_rows"],
            THRESHOLD_COLUMNS,
            table_key="threshold_rows",
            max_width=max_table_width,
            styles=styles,
        ),
        *_pdf_trailing_table_sections(payload, styles, max_table_width),
        _pdf_section_heading(styles, "场景边界说明"),
        _pdf_body(styles, _normalize_text(triage.get("classification_semantics", ""))),
        _pdf_body(styles, "<br/>".join(payload["scenario_guardrails"])),
        Spacer(1, 6),
        _pdf_body(styles, f"生成时间：{payload['generated_at']}"),
    ]

    document.build(story)
    return buffer.getvalue()


def build_report_content(
    repository: ArtifactRepository, export_format: ReportExportFormat
) -> str | bytes:
    if export_format == "html":
        return build_report_html(repository)
    if export_format == "md":
        return build_report_markdown(repository)
    if export_format == "json":
        return build_report_json(repository)
    if export_format == "pdf":
        return build_report_pdf(repository)
    raise ValueError(f"Unsupported report format: {export_format}")


def get_report_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    for export_format, file_suffix in REPORT_FILE_SUFFIXES.items():
        if suffix == file_suffix:
            return REPORT_MEDIA_TYPES[export_format]
    return "application/octet-stream"


def write_report(
    repository: ArtifactRepository,
    report_root: Path,
    export_format: ReportExportFormat = "html",
) -> Path:
    report_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(REPORT_TIMESTAMP_FORMAT)
    unique_id = uuid4().hex[:REPORT_ID_LENGTH]
    suffix = REPORT_FILE_SUFFIXES[export_format]
    path = report_root / f"{REPORT_FILENAME_PREFIX}-{timestamp}-{unique_id}{suffix}"
    content = build_report_content(repository, export_format)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path
