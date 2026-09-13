from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tigramite import data_processing as pp
from tigramite.independence_tests.parcorr import ParCorr
from tigramite.pcmci import PCMCI

from water_ai.utils.io import ensure_dir, save_json

DOMAIN_KEYWORDS = {
    "turbidity": ["turbidity", "clarity", "transparency", "ntu"],
    "sediment": ["sediment", "suspended sediment", "ssc", "suspended solids", "resuspension"],
    "rainfall": ["rainfall", "precipitation", "storm", "rain"],
    "runoff": ["runoff", "nonpoint", "surface flow", "stormwater"],
    "flow": [
        "discharge",
        "streamflow",
        "flow velocity",
        "flow",
        "hydrodynamic",
        "water level",
        "backflow",
        "tidal",
    ],
    "agriculture": ["agriculture", "farmland", "cropland"],
    "nutrients": ["nitrogen", "phosphorus", "nutrient", "ammonia", "tp", "tn"],
    "algae": ["algae", "chlorophyll", "phytoplankton", "bloom"],
    "self_purification": ["self-purification", "self purification", "degradation", "settling"],
    "water_quality": ["water quality", "dissolved oxygen", "conductivity", "cod"],
    "wind": ["wind", "mixing", "wave"],
}

FEATURE_DOMAIN_MAP = {
    "water_temp": ["water_quality"],
    "ph": ["water_quality"],
    "dissolved_oxygen": ["water_quality", "self_purification"],
    "conductivity": ["flow", "water_quality"],
    "turbidity": ["turbidity", "sediment"],
    "codmn": ["water_quality", "self_purification"],
    "nh3_n": ["nutrients"],
    "tp": ["nutrients"],
    "tn": ["nutrients"],
    "pressure": ["flow"],
    "air_temp": ["rainfall"],
    "humidity": ["rainfall"],
    "precipitation": ["rainfall"],
    "wind_speed": ["wind"],
    "wind_dir_sin": ["wind"],
    "wind_dir_cos": ["wind"],
    "precipitation_3d": ["rainfall", "runoff"],
    "precipitation_7d": ["rainfall", "runoff"],
    "pressure_drop": ["rainfall", "flow"],
    "resuspension_index": ["sediment", "wind"],
    "runoff_proxy": ["runoff", "rainfall"],
    "nutrient_risk_index": ["nutrients", "agriculture"],
    "self_purification_index": ["self_purification", "water_quality"],
    "mixing_proxy": ["wind", "flow"],
    "settling_index": ["self_purification", "sediment"],
    "hydrodynamic_intensity": ["flow", "wind"],
    "conductivity_anomaly": ["flow", "water_quality"],
    "water_air_temp_gap": ["water_quality"],
    "dayofyear_sin": ["rainfall"],
    "dayofyear_cos": ["rainfall"],
    "ndti_annual_proxy": ["turbidity", "sediment"],
    "ndti_annual_local_std": ["turbidity", "sediment"],
    "songpu_flow_m3s": ["flow", "sediment"],
    "songpu_water_level_m": ["flow"],
    "huangdu_flow_m3s": ["flow", "runoff"],
    "huangdu_water_level_m": ["flow"],
    "songpu_flow_m3s_abs": ["flow", "sediment"],
    "songpu_flow_m3s_reverse_flag": ["flow"],
    "songpu_flow_m3s_3d_mean": ["flow", "runoff"],
    "songpu_flow_m3s_7d_mean": ["flow", "self_purification"],
    "huangdu_flow_m3s_abs": ["flow", "runoff"],
    "huangdu_flow_m3s_reverse_flag": ["flow"],
    "huangdu_flow_m3s_3d_mean": ["flow", "runoff"],
    "huangdu_flow_m3s_7d_mean": ["flow", "runoff"],
    "songpu_water_level_m_1d_diff": ["flow", "sediment"],
    "songpu_water_level_m_3d_mean": ["flow"],
    "huangdu_water_level_m_1d_diff": ["flow", "runoff"],
    "huangdu_water_level_m_3d_mean": ["flow"],
    "songpu_flow_level_coupling": ["flow", "sediment"],
    "huangdu_flow_level_coupling": ["flow", "runoff"],
    "songpu_flow_m3s_1d_diff": ["flow", "sediment"],
    "huangdu_flow_m3s_1d_diff": ["flow", "runoff"],
    "songpu_flow_rise_flag": ["flow"],
    "huangdu_flow_rise_flag": ["flow", "runoff"],
    "songpu_tidal_pumping_proxy": ["flow", "sediment"],
    "songpu_resuspension_potential": ["flow", "sediment"],
    "songpu_flushing_potential": ["flow", "self_purification"],
    "runoff_sediment_pulse": ["runoff", "sediment"],
}

EXPERT_EDGES = [
    ("precipitation", "runoff_proxy", 1.0),
    ("precipitation_3d", "runoff_proxy", 0.9),
    ("precipitation_7d", "runoff_proxy", 1.0),
    ("wind_speed", "resuspension_index", 1.0),
    ("runoff_proxy", "turbidity", 1.0),
    ("resuspension_index", "turbidity", 1.0),
    ("nutrient_risk_index", "turbidity", 0.7),
    ("self_purification_index", "clearness_proxy", 1.0),
    ("settling_index", "clearness_proxy", 0.8),
    ("hydrodynamic_intensity", "turbidity", 0.7),
    ("ndti_annual_proxy", "turbidity", 0.8),
    ("ndti_annual_local_std", "turbidity", 0.4),
    ("songpu_flow_m3s_abs", "turbidity", 1.0),
    ("songpu_flow_m3s_3d_mean", "turbidity", 0.9),
    ("songpu_flow_level_coupling", "turbidity", 1.0),
    ("songpu_water_level_m_1d_diff", "resuspension_index", 0.8),
    ("songpu_flow_m3s_reverse_flag", "turbidity", 0.7),
    ("huangdu_flow_m3s_3d_mean", "runoff_proxy", 0.7),
    ("songpu_flow_m3s_7d_mean", "self_purification_index", 0.4),
    ("songpu_flow_m3s_1d_diff", "turbidity", 0.6),
    ("songpu_tidal_pumping_proxy", "turbidity", 0.9),
    ("songpu_resuspension_potential", "resuspension_index", 1.0),
    ("songpu_flushing_potential", "clearness_proxy", 0.7),
    ("runoff_sediment_pulse", "turbidity", 0.8),
    ("turbidity", "clearness_proxy", 1.0),
]

PCMCI_PRIORITY_FEATURES = [
    "turbidity",
    "conductivity",
    "dissolved_oxygen",
    "nh3_n",
    "tp",
    "tn",
    "precipitation",
    "precipitation_3d",
    "precipitation_7d",
    "wind_speed",
    "pressure",
    "runoff_proxy",
    "resuspension_index",
    "hydrodynamic_intensity",
    "songpu_flow_m3s_abs",
    "songpu_flow_m3s_1d_diff",
    "songpu_water_level_m_1d_diff",
    "songpu_tidal_pumping_proxy",
    "songpu_resuspension_potential",
    "songpu_flushing_potential",
    "runoff_sediment_pulse",
]


def _infer_domains(text: str) -> set[str]:
    lower_text = text.lower()
    found = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            found.add(domain)
    return found


def build_feature_graph_priors(
    rag_artifacts_dir: str | Path,
    feature_columns: list[str],
    output_dir: str | Path,
    causal_df: pd.DataFrame | None = None,
    pcmci_tau_max: int = 3,
    pcmci_pc_alpha: float = 0.2,
    pcmci_alpha_level: float = 0.05,
) -> tuple[np.ndarray, dict[str, Any]]:
    output_dir = ensure_dir(output_dir)
    intermediate_dir = ensure_dir(Path(output_dir) / "intermediate")

    relationships_path = Path(rag_artifacts_dir) / "create_final_relationships.parquet"
    relationships_df = pd.read_parquet(relationships_path)

    domain_weights: defaultdict[tuple[str, str], float] = defaultdict(float)
    evidence_counter = 0

    for row in relationships_df.itertuples(index=False):
        source_text = str(getattr(row, "source", ""))
        target_text = str(getattr(row, "target", ""))
        description_text = str(getattr(row, "description", ""))
        weight = float(getattr(row, "weight", 1.0) or 1.0)

        source_domains = _infer_domains(" ".join([source_text, description_text]))
        target_domains = _infer_domains(" ".join([target_text, description_text]))
        if not source_domains and not target_domains:
            continue

        if not source_domains:
            source_domains = target_domains
        if not target_domains:
            target_domains = source_domains

        evidence_counter += 1
        for left in source_domains:
            for right in target_domains:
                domain_weights[(left, right)] += weight
                domain_weights[(right, left)] += weight

    domain_edges = pd.DataFrame(
        [
            {"source_domain": left, "target_domain": right, "weight": weight}
            for (left, right), weight in domain_weights.items()
        ]
    ).sort_values("weight", ascending=False)
    domain_edges.to_csv(
        intermediate_dir / "domain_graph_edges.csv", index=False, encoding="utf-8-sig"
    )

    feature_count = len(feature_columns)
    adjacency = np.zeros((feature_count, feature_count), dtype=np.float32)
    feature_to_domains = {
        feature: FEATURE_DOMAIN_MAP.get(feature, ["water_quality"]) for feature in feature_columns
    }

    for i, left in enumerate(feature_columns):
        adjacency[i, i] = 1.0
        left_domains = feature_to_domains[left]
        for j in range(i + 1, feature_count):
            right = feature_columns[j]
            right_domains = feature_to_domains[right]
            weight = 0.0
            for left_domain in left_domains:
                for right_domain in right_domains:
                    weight = max(weight, domain_weights.get((left_domain, right_domain), 0.0))
            adjacency[i, j] = weight
            adjacency[j, i] = weight

    for source_feature, target_feature, weight in EXPERT_EDGES:
        if source_feature not in feature_columns or target_feature not in feature_columns:
            continue
        i = feature_columns.index(source_feature)
        j = feature_columns.index(target_feature)
        adjacency[i, j] += weight
        adjacency[j, i] += weight

    pcmci_summary: dict[str, Any] | None = None
    if causal_df is not None and len(causal_df) > max(30, pcmci_tau_max * 10):
        pcmci_summary = _build_pcmci_adjacency(
            causal_df=causal_df,
            feature_columns=feature_columns,
            adjacency=adjacency,
            output_dir=intermediate_dir,
            tau_max=pcmci_tau_max,
            pc_alpha=pcmci_pc_alpha,
            alpha_level=pcmci_alpha_level,
        )

    if np.max(adjacency) > 0.0:
        adjacency = adjacency / float(np.max(adjacency))

    adjacency_df = pd.DataFrame(adjacency, index=feature_columns, columns=feature_columns)
    adjacency_df.to_csv(
        intermediate_dir / "feature_graph_adjacency.csv", encoding="utf-8-sig"
    )

    summary = {
        "relationships_path": str(relationships_path),
        "relationship_rows": int(len(relationships_df)),
        "relationship_rows_with_domain_evidence": int(evidence_counter),
        "feature_count": feature_count,
        "feature_to_domains": feature_to_domains,
        "pcmci_summary": pcmci_summary,
    }
    save_json(summary, intermediate_dir / "feature_graph_summary.json")
    return adjacency, summary


def _build_pcmci_adjacency(
    causal_df: pd.DataFrame,
    feature_columns: list[str],
    adjacency: np.ndarray,
    output_dir: Path,
    tau_max: int,
    pc_alpha: float,
    alpha_level: float,
) -> dict[str, Any]:
    selected_features = [
        feature for feature in PCMCI_PRIORITY_FEATURES if feature in feature_columns
    ]
    if "turbidity" not in selected_features and "turbidity" in feature_columns:
        selected_features = ["turbidity", *selected_features]
    if len(selected_features) < 3:
        return {
            "enabled": False,
            "reason": "too_few_features_for_pcmci",
            "selected_features": selected_features,
        }

    causal_matrix = causal_df[selected_features].copy()
    causal_matrix = causal_matrix.interpolate(limit_direction="both").ffill().bfill()
    tigramite_df = pp.DataFrame(
        causal_matrix.to_numpy(dtype=np.float64),
        var_names=selected_features,
    )
    pcmci = PCMCI(dataframe=tigramite_df, cond_ind_test=ParCorr())
    results = pcmci.run_pcmci(
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        alpha_level=alpha_level,
    )

    graph = results["graph"]
    val_matrix = results["val_matrix"]
    p_matrix = results["p_matrix"]

    edge_rows = []
    for source_index, source_name in enumerate(selected_features):
        for target_index, target_name in enumerate(selected_features):
            if source_index == target_index:
                continue
            best_weight = 0.0
            best_lag = None
            best_p = None
            for lag in range(1, tau_max + 1):
                if graph[source_index, target_index, lag] != "-->":
                    continue
                weight = abs(float(val_matrix[source_index, target_index, lag]))
                if weight <= 0.0:
                    continue
                if weight > best_weight:
                    best_weight = weight
                    best_lag = lag
                    best_p = float(p_matrix[source_index, target_index, lag])
            if best_lag is None:
                continue
            source_full_index = feature_columns.index(source_name)
            target_full_index = feature_columns.index(target_name)
            adjacency[source_full_index, target_full_index] += best_weight
            adjacency[target_full_index, source_full_index] += 0.5 * best_weight
            edge_rows.append(
                {
                    "source_feature": source_name,
                    "target_feature": target_name,
                    "lag_days": int(best_lag),
                    "effect_strength": float(best_weight),
                    "p_value": float(best_p if best_p is not None else 1.0),
                }
            )

    if edge_rows:
        pcmci_edges = pd.DataFrame(edge_rows).sort_values(
            ["effect_strength", "p_value"], ascending=[False, True]
        )
    else:
        pcmci_edges = pd.DataFrame(
            columns=["source_feature", "target_feature", "lag_days", "effect_strength", "p_value"]
        )
    pcmci_path = output_dir / "pcmci_discovered_edges.csv"
    pcmci_edges.to_csv(pcmci_path, index=False, encoding="utf-8-sig")

    top_turbidity_parents = (
        pcmci_edges[pcmci_edges["target_feature"] == "turbidity"]
        .head(15)
        .to_dict(orient="records")
    )
    top_hydrodynamics_edges = (
        pcmci_edges[
            pcmci_edges["source_feature"].str.contains("songpu|huangdu|hydro|runoff", regex=True)
        ]
        .head(15)
        .to_dict(orient="records")
    )
    return {
        "enabled": True,
        "selected_features": selected_features,
        "tau_max": int(tau_max),
        "pc_alpha": float(pc_alpha),
        "alpha_level": float(alpha_level),
        "discovered_edge_count": int(len(pcmci_edges)),
        "output_csv": str(pcmci_path),
        "top_turbidity_parents": top_turbidity_parents,
        "top_hydrodynamics_edges": top_hydrodynamics_edges,
    }
