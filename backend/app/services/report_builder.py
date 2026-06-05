from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from backend.app.services.artifact_repository import ArtifactRepository


def _card_list(items: list[str]) -> str:
    return "".join(f"<li>{escape(str(item))}</li>" for item in items)


def _table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "<p class='empty'>No rows available.</p>"
    header = "".join(f"<th>{escape(label)}</th>" for _, label in columns)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{escape('' if row.get(key) is None else str(row.get(key)))}</td>"
            for key, _ in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def build_report_html(repository: ArtifactRepository) -> str:
    dashboard = repository.dashboard()
    predictions = repository.predictions(model=None, split="test")
    diagnostics = repository.diagnostics()
    triage = repository.scenario_triage()
    thresholds = repository.thresholds(feature=None)
    boundary = repository.boundary()
    sensitivity = repository.sensitivity()

    prediction_rows = predictions["series"][:12]
    threshold_rows = thresholds["summary"][:12]
    priority_rows = dashboard["high_priority_days"][:10]
    sobol_rows = sensitivity["sobol"].get("top_factors", [])[:8]
    process_rows = diagnostics["process_decomposition"][:7]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>WaterExpert Software Report</title>
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
        <h1>WaterExpert Software Report</h1>
        <p>This report summarizes the current Wusongkou single-station prototype from the repository-root runtime inside the WaterExpert software branch. It is intended for result review, not for operational control claims.</p>
        <div class="meta">
          <div><strong>Station</strong>{escape(str(dashboard["station_profile"]["station_name"]))}</div>
          <div><strong>River</strong>{escape(str(dashboard["station_profile"]["river"]))}</div>
          <div><strong>Scope</strong>{escape(str(dashboard["prototype_scope"]))}</div>
          <div><strong>Matched rows</strong>{escape(str(dashboard["station_profile"]["matched_model_rows"]))}</div>
        </div>
      </div>
      <div class="panel warning">
        <h3>Guardrails</h3>
        <ul>{_card_list(dashboard["guardrails"])}</ul>
      </div>
    </section>

    <h2>Model Snapshot</h2>
    <div class="panel">
      <p>Best turbidity model in the verified test window: <strong>{escape(str(predictions["selected_model"]))}</strong></p>
      <ul class="chips">
        <li>Turbidity R2: {escape(str(dashboard["test_models"][predictions["selected_model"]].get("turbidity_r2")))}</li>
        <li>Turbidity RMSE: {escape(str(dashboard["test_models"][predictions["selected_model"]].get("turbidity_rmse")))}</li>
        <li>Clearness R2: {escape(str(dashboard["test_models"][predictions["selected_model"]].get("clearness_r2")))}</li>
        <li>Clearness RMSE: {escape(str(dashboard["test_models"][predictions["selected_model"]].get("clearness_rmse")))}</li>
      </ul>
    </div>

    <h2>High-Priority Days</h2>
    <div class="panel">
      {_table(priority_rows, [
        ("target_date", "Date"),
        ("primary_scenario", "Scenario"),
        ("risk_band", "Risk"),
        ("predicted_critical_transition_prob", "Critical Transition Prob"),
        ("evidence_summary", "Evidence Summary"),
      ])}
    </div>

    <h2>Prediction Preview</h2>
    <div class="panel">
      {_table(prediction_rows, [
        ("target_date", "Date"),
        ("actual_turbidity", "Actual Turbidity"),
        ("predicted_turbidity", "Predicted Turbidity"),
        ("actual_clearness", "Actual Clearness"),
        ("predicted_clearness", "Predicted Clearness"),
        ("predicted_critical_transition_prob", "Critical Transition Prob"),
      ])}
    </div>

    <h2>Diagnosis Summary</h2>
    <div class="panel">
      {_table(diagnostics["factor_summary"].get("top_driver_features", []), [
        ("feature", "Feature"),
        ("feature_label", "Label"),
        ("driver_score", "Driver Score"),
      ])}
    </div>

    <h2>Mechanism Process Decomposition</h2>
    <div class="panel">
      {_table(process_rows, [
        ("process_label", "Process"),
        ("direction", "Direction"),
        ("mean_contribution", "Mean Contribution"),
        ("std_contribution", "Std"),
        ("max_contribution", "Max"),
      ])}
    </div>

    <h2>Threshold Retrieval</h2>
    <div class="panel">
      <p>{escape(str(thresholds["threshold_semantics"]))}</p>
      {_table(threshold_rows, [
        ("feature_label", "Feature"),
        ("threshold", "Threshold"),
        ("unit", "Unit"),
        ("r2_gain", "R2 Gain"),
        ("response_jump", "Response Jump"),
        ("status", "Status"),
      ])}
    </div>

    <h2>Boundary Summary</h2>
    <div class="panel">
      {_table([
        {
          "cmfbe_test_f1": boundary["summary"]["models"]["cmfbe_stgcn"]["test"]["f1"],
          "cmfbe_test_accuracy": boundary["summary"]["models"]["cmfbe_stgcn"]["test"]["accuracy"],
          "mscim_test_f1": boundary["summary"]["models"]["mscim"]["test"]["f1"],
          "overall_positive_rate": boundary["summary"]["overall"]["test"]["positive_rate"],
          "labeled_samples": boundary["summary"]["overall"]["test"]["labeled_samples"],
        }
      ], [
        ("cmfbe_test_f1", "CMFBE Test F1"),
        ("cmfbe_test_accuracy", "CMFBE Test Accuracy"),
        ("mscim_test_f1", "MSCIM Test F1"),
        ("overall_positive_rate", "Positive Rate"),
        ("labeled_samples", "Labeled Samples"),
      ])}
    </div>

    <h2>Sobol and Counterfactual Signals</h2>
    <div class="panel">
      {_table(sobol_rows, [
        ("factor_label", "Factor"),
        ("first_order_index", "First Order"),
        ("total_order_index", "Total Order"),
        ("interaction_strength", "Interaction"),
      ])}
    </div>

    <h2>Scenario Guardrails</h2>
    <div class="panel">
      <p>{escape(str(triage.get("classification_semantics", "")))}</p>
      <ul>{_card_list([
        "Scenario labels are empirical triage outputs, not validated governance classes.",
        "Threshold retrieval shows current prototype breakpoints, not calibrated physical control boundaries.",
        "Response playbook outputs support analyst follow-up and monitoring prioritization only.",
      ])}</ul>
    </div>

    <p>Generated at {escape(datetime.now().isoformat(timespec="seconds"))}</p>
  </main>
</body>
</html>"""


def write_report(repository: ArtifactRepository, report_root: Path) -> Path:
    report_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = report_root / f"waterexpert-software-report-{timestamp}.html"
    path.write_text(build_report_html(repository), encoding="utf-8")
    return path
