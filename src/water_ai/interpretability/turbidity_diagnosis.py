from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from water_ai.utils.io import ensure_dir, save_json

FEATURE_LABELS = {
    "water_temp": "水温",
    "ph": "pH",
    "dissolved_oxygen": "溶解氧",
    "conductivity": "电导率",
    "turbidity": "浊度",
    "codmn": "高锰酸盐指数",
    "nh3_n": "氨氮",
    "tp": "总磷",
    "tn": "总氮",
    "pressure": "气压",
    "air_temp": "气温",
    "humidity": "相对湿度",
    "precipitation": "当日降水",
    "wind_speed": "风速",
    "wind_dir_sin": "风向正弦分量",
    "wind_dir_cos": "风向余弦分量",
    "precipitation_3d": "近3日降水累计",
    "precipitation_7d": "近7日降水累计",
    "pressure_drop": "气压骤降强度",
    "resuspension_index": "底泥再悬浮指数",
    "runoff_proxy": "径流代理指数",
    "nutrient_risk_index": "营养盐风险指数",
    "self_purification_index": "自净指数",
    "mixing_proxy": "混合扰动指数",
    "settling_index": "沉降指数",
    "hydrodynamic_intensity": "水动力强度指数",
    "conductivity_anomaly": "电导率异常",
    "water_air_temp_gap": "水气温差",
    "dayofyear_sin": "年周期正弦分量",
    "dayofyear_cos": "年周期余弦分量",
}

DOMAIN_LABELS = {
    "turbidity": "浊度响应",
    "sediment": "泥沙再悬浮",
    "rainfall": "降雨过程",
    "runoff": "径流输入",
    "flow": "水动力过程",
    "agriculture": "农业面源",
    "nutrients": "营养盐负荷",
    "algae": "藻类过程",
    "self_purification": "自净沉降",
    "water_quality": "水质本底",
    "wind": "风场扰动",
}

SUMMARY_EXCLUDED_FEATURES = {"turbidity"}

FEATURE_LABELS.update(
    {
        "ndti_annual_proxy": "\u5e74\u5ea6NDTI\u6d4a\u5ea6\u4ee3\u7406",
        "ndti_annual_local_std": "\u5e74\u5ea6NDTI\u5c40\u5730\u53d8\u5f02",
        "songpu_flow_m3s": "\u677e\u6d66\u5927\u6865\u6d41\u91cf",
        "songpu_water_level_m": "\u677e\u6d66\u5927\u6865\u6c34\u4f4d",
        "huangdu_flow_m3s": "\u9ec4\u6e21\u6d41\u91cf",
        "huangdu_water_level_m": "\u9ec4\u6e21\u6c34\u4f4d",
        "songpu_flow_m3s_abs": "\u677e\u6d66\u5927\u6865\u6d41\u91cf\u7edd\u5bf9\u503c",
        "songpu_flow_m3s_reverse_flag": "\u677e\u6d66\u5927\u6865\u53cd\u5411\u6d41\u6807\u8bb0",
        "songpu_flow_m3s_3d_mean": "\u677e\u6d66\u5927\u6865\u6d41\u91cf3\u65e5\u5747\u503c",
        "songpu_flow_m3s_7d_mean": "\u677e\u6d66\u5927\u6865\u6d41\u91cf7\u65e5\u5747\u503c",
        "huangdu_flow_m3s_abs": "\u9ec4\u6e21\u6d41\u91cf\u7edd\u5bf9\u503c",
        "huangdu_flow_m3s_reverse_flag": "\u9ec4\u6e21\u53cd\u5411\u6d41\u6807\u8bb0",
        "huangdu_flow_m3s_3d_mean": "\u9ec4\u6e21\u6d41\u91cf3\u65e5\u5747\u503c",
        "huangdu_flow_m3s_7d_mean": "\u9ec4\u6e21\u6d41\u91cf7\u65e5\u5747\u503c",
        "songpu_water_level_m_1d_diff": "\u677e\u6d66\u5927\u6865\u6c34\u4f4d\u65e5\u53d8\u5316",
        "songpu_water_level_m_3d_mean": "\u677e\u6d66\u5927\u6865\u6c34\u4f4d3\u65e5\u5747\u503c",
        "huangdu_water_level_m_1d_diff": "\u9ec4\u6e21\u6c34\u4f4d\u65e5\u53d8\u5316",
        "huangdu_water_level_m_3d_mean": "\u9ec4\u6e21\u6c34\u4f4d3\u65e5\u5747\u503c",
        "songpu_flow_level_coupling": "\u677e\u6d66\u5927\u6865\u6d41\u91cf-\u6c34\u4f4d\u8026\u5408",
        "huangdu_flow_level_coupling": "\u9ec4\u6e21\u6d41\u91cf-\u6c34\u4f4d\u8026\u5408",
        "songpu_flow_m3s_1d_diff": "\u677e\u6d66\u5927\u6865\u6d41\u91cf\u65e5\u53d8\u5316",
        "huangdu_flow_m3s_1d_diff": "\u9ec4\u6e21\u6d41\u91cf\u65e5\u53d8\u5316",
        "songpu_flow_rise_flag": "\u677e\u6d66\u5927\u6865\u6d41\u91cf\u4e0a\u6da8\u6807\u8bb0",
        "huangdu_flow_rise_flag": "\u9ec4\u6e21\u6d41\u91cf\u4e0a\u6da8\u6807\u8bb0",
        "songpu_tidal_pumping_proxy": "\u677e\u6d66\u5927\u6865\u6f6e\u6c50\u56de\u6d41\u4ee3\u7406",
        "songpu_resuspension_potential": "\u677e\u6d66\u5927\u6865\u518d\u60ac\u6d6e\u6f5c\u529b",
        "songpu_flushing_potential": "\u677e\u6d66\u5927\u6865\u51b2\u5237\u6f5c\u529b",
        "runoff_sediment_pulse": "\u5f84\u6d41-\u6ce5\u6c99\u8109\u51b2\u6307\u6807",
    }
)


def _to_device(batch: dict[str, Any], device: torch.device) -> dict[str, Any]:
    moved = {}
    for key, value in batch.items():
        moved[key] = value.to(device) if torch.is_tensor(value) else value
    return moved


def _label_feature(feature_name: str) -> str:
    return FEATURE_LABELS.get(feature_name, feature_name)


def _label_domains(domains: list[str]) -> str:
    return " / ".join(DOMAIN_LABELS.get(domain, domain) for domain in domains)


def diagnose_mscim_turbidity(
    model: torch.nn.Module,
    loader: torch.utils.data.DataLoader,
    feature_columns: list[str],
    feature_to_domains: dict[str, list[str]],
    device: torch.device,
    output_dir: str | Path,
    top_k: int = 3,
) -> dict[str, Path]:
    diagnosis_dir = ensure_dir(Path(output_dir) / "diagnosis")
    detail_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    domain_rows: list[dict[str, Any]] = []

    model.eval()
    with torch.no_grad():
        for batch in loader:
            batch = _to_device(batch, device)
            base_outputs = model(batch["x"], batch["x_raw"])
            base_turbidity = base_outputs["turbidity_pred"].detach().cpu().numpy()
            base_clearness = base_outputs["clearness_pred"].detach().cpu().numpy()
            causal_saliency = base_outputs["causal_saliency"].detach().cpu().numpy()
            raw_last = batch["x_raw"][:, -1, :].detach().cpu().numpy()
            actual_turbidity = batch["y_turbidity"].detach().cpu().numpy()
            actual_clearness = batch["y_clearness"].detach().cpu().numpy()

            perturbation_effects = []
            for feature_index in range(len(feature_columns)):
                perturbed_x = batch["x"].clone()
                perturbed_x[:, :, feature_index] = 0.0
                perturbed_outputs = model(perturbed_x, batch["x_raw"])
                effect = (
                    base_turbidity
                    - perturbed_outputs["turbidity_pred"].detach().cpu().numpy()
                )
                perturbation_effects.append(effect)

            effect_matrix = np.stack(perturbation_effects, axis=1)
            driver_scores = np.clip(effect_matrix, a_min=0.0, a_max=None) * causal_saliency
            inhibitor_scores = np.clip(-effect_matrix, a_min=0.0, a_max=None) * causal_saliency

            for sample_index, target_date in enumerate(batch["target_date"]):
                domain_driver_scores: defaultdict[str, float] = defaultdict(float)
                domain_inhibitor_scores: defaultdict[str, float] = defaultdict(float)

                for feature_index, feature_name in enumerate(feature_columns):
                    domains = feature_to_domains.get(feature_name, ["water_quality"])
                    driver_score = float(driver_scores[sample_index, feature_index])
                    inhibitor_score = float(inhibitor_scores[sample_index, feature_index])
                    effect_score = float(effect_matrix[sample_index, feature_index])
                    saliency_score = float(causal_saliency[sample_index, feature_index])
                    raw_value = float(raw_last[sample_index, feature_index])

                    detail_rows.append(
                        {
                            "target_date": target_date,
                            "actual_turbidity": float(actual_turbidity[sample_index]),
                            "predicted_turbidity": float(base_turbidity[sample_index]),
                            "actual_clearness": float(actual_clearness[sample_index]),
                            "predicted_clearness": float(base_clearness[sample_index]),
                            "feature": feature_name,
                            "feature_label": _label_feature(feature_name),
                            "domains": "|".join(domains),
                            "domain_labels": _label_domains(domains),
                            "last_raw_value": raw_value,
                            "causal_saliency": saliency_score,
                            "perturbation_effect": effect_score,
                            "driver_score": driver_score,
                            "inhibitor_score": inhibitor_score,
                        }
                    )
                    if feature_name not in SUMMARY_EXCLUDED_FEATURES:
                        for domain in domains:
                            domain_driver_scores[domain] += driver_score
                            domain_inhibitor_scores[domain] += inhibitor_score

                for domain_name, score in domain_driver_scores.items():
                    domain_rows.append(
                        {
                            "target_date": target_date,
                            "domain": domain_name,
                            "domain_label": DOMAIN_LABELS.get(domain_name, domain_name),
                            "direction": "driver",
                            "score": float(score),
                        }
                    )
                for domain_name, score in domain_inhibitor_scores.items():
                    domain_rows.append(
                        {
                            "target_date": target_date,
                            "domain": domain_name,
                            "domain_label": DOMAIN_LABELS.get(domain_name, domain_name),
                            "direction": "inhibitor",
                            "score": float(score),
                        }
                    )

                ranking_driver_scores = driver_scores[sample_index].copy()
                ranking_inhibitor_scores = inhibitor_scores[sample_index].copy()
                for feature_index, feature_name in enumerate(feature_columns):
                    if feature_name in SUMMARY_EXCLUDED_FEATURES:
                        ranking_driver_scores[feature_index] = -np.inf
                        ranking_inhibitor_scores[feature_index] = -np.inf

                top_driver_indices = np.argsort(ranking_driver_scores)[::-1][:top_k]
                top_inhibitor_indices = np.argsort(ranking_inhibitor_scores)[::-1][:top_k]
                summary_row = {
                    "target_date": target_date,
                    "actual_turbidity": float(actual_turbidity[sample_index]),
                    "predicted_turbidity": float(base_turbidity[sample_index]),
                    "actual_clearness": float(actual_clearness[sample_index]),
                    "predicted_clearness": float(base_clearness[sample_index]),
                }

                sorted_driver_domains = sorted(
                    domain_driver_scores.items(), key=lambda item: item[1], reverse=True
                )
                sorted_inhibitor_domains = sorted(
                    domain_inhibitor_scores.items(), key=lambda item: item[1], reverse=True
                )
                if sorted_driver_domains:
                    summary_row["dominant_driver_domain"] = DOMAIN_LABELS.get(
                        sorted_driver_domains[0][0], sorted_driver_domains[0][0]
                    )
                    summary_row["dominant_driver_domain_score"] = float(sorted_driver_domains[0][1])
                if sorted_inhibitor_domains:
                    summary_row["dominant_inhibitor_domain"] = DOMAIN_LABELS.get(
                        sorted_inhibitor_domains[0][0], sorted_inhibitor_domains[0][0]
                    )
                    summary_row["dominant_inhibitor_domain_score"] = float(
                        sorted_inhibitor_domains[0][1]
                    )

                for rank, feature_index in enumerate(top_driver_indices, start=1):
                    feature_name = feature_columns[feature_index]
                    domains = feature_to_domains.get(feature_name, ["water_quality"])
                    summary_row[f"top_driver_{rank}_feature"] = feature_name
                    summary_row[f"top_driver_{rank}_label"] = _label_feature(feature_name)
                    summary_row[f"top_driver_{rank}_domains"] = _label_domains(domains)
                    summary_row[f"top_driver_{rank}_score"] = float(
                        driver_scores[sample_index, feature_index]
                    )

                for rank, feature_index in enumerate(top_inhibitor_indices, start=1):
                    feature_name = feature_columns[feature_index]
                    domains = feature_to_domains.get(feature_name, ["water_quality"])
                    summary_row[f"top_inhibitor_{rank}_feature"] = feature_name
                    summary_row[f"top_inhibitor_{rank}_label"] = _label_feature(feature_name)
                    summary_row[f"top_inhibitor_{rank}_domains"] = _label_domains(domains)
                    summary_row[f"top_inhibitor_{rank}_score"] = float(
                        inhibitor_scores[sample_index, feature_index]
                    )

                summary_rows.append(summary_row)

    detail_df = pd.DataFrame(detail_rows).sort_values(
        ["target_date", "driver_score", "inhibitor_score"], ascending=[True, False, False]
    )
    summary_df = pd.DataFrame(summary_rows).sort_values("target_date")
    domain_df = pd.DataFrame(domain_rows)

    detail_path = diagnosis_dir / "mscim_turbidity_factor_diagnosis_details.csv"
    summary_path = diagnosis_dir / "mscim_turbidity_factor_diagnosis_summary.csv"
    domain_path = diagnosis_dir / "mscim_turbidity_domain_diagnosis.csv"
    detail_df.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    if not domain_df.empty:
        domain_agg_df = (
            domain_df.groupby(["direction", "domain", "domain_label"], as_index=False)["score"]
            .mean()
            .sort_values(["direction", "score"], ascending=[True, False])
        )
    else:
        domain_agg_df = pd.DataFrame(columns=["direction", "domain", "domain_label", "score"])
    domain_agg_df.to_csv(domain_path, index=False, encoding="utf-8-sig")

    summary_detail_df = detail_df[~detail_df["feature"].isin(SUMMARY_EXCLUDED_FEATURES)].copy()

    top_driver_features_df = (
        summary_detail_df.groupby(["feature", "feature_label"], as_index=False)["driver_score"]
        .mean()
        .sort_values("driver_score", ascending=False)
        .head(10)
    )
    top_inhibitor_features_df = (
        summary_detail_df.groupby(["feature", "feature_label"], as_index=False)["inhibitor_score"]
        .mean()
        .sort_values("inhibitor_score", ascending=False)
        .head(10)
    )

    high_event_df = summary_df.sort_values("actual_turbidity", ascending=False).head(10)
    markdown_lines = [
        "# MSCIM 致浊因子诊断总结",
        "",
        "## 1. 平均主导致浊因子 Top10",
        "",
    ]
    for row in top_driver_features_df.itertuples(index=False):
        markdown_lines.append(
            f"- {row.feature_label}（{row.feature}）: {row.driver_score:.4f}"
        )

    markdown_lines.extend(["", "## 2. 平均主抑浊因子 Top10", ""])
    for row in top_inhibitor_features_df.itertuples(index=False):
        markdown_lines.append(
            f"- {row.feature_label}（{row.feature}）: {row.inhibitor_score:.4f}"
        )

    markdown_lines.extend(["", "## 3. 高浊度事件诊断样例", ""])
    for row in high_event_df.itertuples(index=False):
        markdown_lines.append(
            f"- {row.target_date}: 实测浊度 {row.actual_turbidity:.2f}，诊断主因子为 "
            f"{row.top_driver_1_label}、{row.top_driver_2_label}、{row.top_driver_3_label}"
        )

    markdown_path = diagnosis_dir / "mscim_turbidity_factor_diagnosis_summary.md"
    markdown_path.write_text("\n".join(markdown_lines), encoding="utf-8")

    summary_json = {
        "top_driver_features": top_driver_features_df.to_dict(orient="records"),
        "top_inhibitor_features": top_inhibitor_features_df.to_dict(orient="records"),
        "top_driver_domains": domain_agg_df[domain_agg_df["direction"] == "driver"]
        .head(10)
        .to_dict(orient="records"),
        "top_inhibitor_domains": domain_agg_df[domain_agg_df["direction"] == "inhibitor"]
        .head(10)
        .to_dict(orient="records"),
    }
    summary_json_path = diagnosis_dir / "mscim_turbidity_factor_diagnosis_summary.json"
    save_json(summary_json, summary_json_path)

    return {
        "detail_csv": detail_path,
        "summary_csv": summary_path,
        "domain_csv": domain_path,
        "summary_md": markdown_path,
        "summary_json": summary_json_path,
    }
