import {
  ANALYSIS_DEFAULT_TAB,
  escapeHtml,
  formatDomainLabel,
  formatFactorLabel,
  formatMaybeDate,
  formatNumber,
  formatPriorityDate,
  formatPriorityScenario,
  formatProcessDirection,
  formatRiskBandLabel,
  getElement,
  hasElement,
  maxNumeric,
  renderMutedMessage,
  renderTable,
  setHtml,
  setText,
  state,
  summarizeEvidence,
} from "./base.js";
import { buildApiUrl, fetchJsonSafe } from "./api.js";
import { renderDashboardPriorityFeed, renderDiagnosticsOverview } from "./dashboard.js";

export function renderDiagnosticsDetailed() {
  const drivers = state.diagnostics?.factor_summary?.top_driver_features || [];
  const maxScore = maxNumeric(drivers.map((item) => item.driver_score), 1);
  setHtml(
    "driverBars",
    drivers.length
      ? drivers.slice(0, 8).map((item) => {
          const width = ((Number(item.driver_score) || 0) / maxScore) * 100;
          return `
            <div class="bar-row">
              <div class="bar-label"><span>${escapeHtml(item.feature_label || item.feature)}</span><strong>${escapeHtml(formatNumber(item.driver_score))}</strong></div>
              <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
            </div>`;
        }).join("")
      : `<p class='muted'>暂无主导因子结果。</p>`
  );
}

function getDominantScenario() {
  const topPriorityScenario = state.triage?.high_priority_days?.[0]?.primary_scenario;
  if (topPriorityScenario) {
    return topPriorityScenario;
  }
  const scenarioCounts = Object.entries(state.triage?.scenario_counts || {});
  if (!scenarioCounts.length) {
    return "";
  }
  return scenarioCounts.sort((left, right) => Number(right[1]) - Number(left[1]))[0][0];
}

function getStrongestProcess(direction) {
  const processes = (state.diagnostics?.process_decomposition || []).filter((item) => item.direction === direction);
  if (!processes.length) {
    return null;
  }
  return processes.sort((left, right) => Number(right.mean_contribution || 0) - Number(left.mean_contribution || 0))[0];
}

export function renderProcessEvidenceDetailed() {
  const container = getElement("processTable");
  if (!container) {
    return;
  }
  const processes = state.diagnostics?.process_decomposition || [];
  if (!processes.length) {
    container.innerHTML = `<p class='muted'>机理分解暂不可用。</p>`;
    return;
  }
  const groups = [
    { key: "source", title: "推高风险的来源过程" },
    { key: "sink", title: "提供缓冲的过程" },
  ];
  container.innerHTML = `
    <div class="process-group-grid">
      ${groups.map((group) => {
        const rows = processes.filter((item) => item.direction === group.key);
        return `
          <section class="process-group">
            <div class="process-group-head">
              <h3>${escapeHtml(group.title)}</h3>
              <span class="process-group-meta">${escapeHtml(`${rows.length} 项`)}</span>
            </div>
            <div class="process-card-list">
              ${rows.map((item) => `
                <article class="process-card">
                  <div class="process-card-head">
                    <strong>${escapeHtml(item.process_label || item.process_key)}</strong>
                    <span>${escapeHtml(formatProcessDirection(item.direction))}</span>
                  </div>
                  <div class="process-card-metrics">
                    <span>均值贡献 ${escapeHtml(formatNumber(item.mean_contribution, 2))}</span>
                    <span>峰值 ${escapeHtml(formatNumber(item.max_contribution, 2))}</span>
                  </div>
                </article>
              `).join("")}
            </div>
          </section>
        `;
      }).join("")}
    </div>
  `;
}

export function renderTriageDetailed() {
  const container = getElement("priorityTable");
  if (!container) {
    return;
  }
  const priorityDays = state.triage?.high_priority_days || [];
  if (!priorityDays.length) {
    container.innerHTML = `<p class='muted'>暂无高优先事件。</p>`;
    return;
  }
  container.innerHTML = `
    <div class="analysis-priority-stack">
      ${priorityDays.slice(0, 10).map((item) => {
        const evidence = summarizeEvidence(item.evidence_summary, 3);
        const playbook = state.playbook?.scenario_response_playbook?.[item.primary_scenario];
        return `
          <article class="analysis-priority-card">
            <div class="analysis-priority-head">
              <div class="analysis-priority-title">
                <strong>${escapeHtml(formatPriorityDate(item.target_date))}</strong>
                <span>${escapeHtml(`转折概率 ${formatNumber(item.predicted_critical_transition_prob, 2)}`)}</span>
              </div>
              <div class="priority-badges">
                <span class="priority-scenario">${escapeHtml(formatPriorityScenario(item))}</span>
                <span class="priority-risk">${escapeHtml(formatRiskBandLabel(item.risk_band))}</span>
              </div>
            </div>
            <div class="priority-facts">
              ${evidence.visibleFacts.map((fact) => `<span class="priority-fact">${escapeHtml(fact)}</span>`).join("")}
              ${evidence.hiddenCount ? `<span class="priority-fact priority-fact-more">另 ${escapeHtml(evidence.hiddenCount)} 项</span>` : ""}
            </div>
            ${playbook?.response_focus ? `<p class="analysis-priority-note">${escapeHtml(playbook.response_focus)}</p>` : ""}
          </article>
        `;
      }).join("")}
    </div>
  `;
}

export function renderSobolDetailed() {
  const container = getElement("sobolTable");
  if (!container) {
    return;
  }
  const factors = state.sensitivity?.sobol?.top_factors || [];
  if (!factors.length) {
    container.innerHTML = `<p class='muted'>敏感性结果暂不可用。</p>`;
    return;
  }
  const maxTotalOrder = maxNumeric(factors.map((item) => item.total_order_index), 1);
  container.innerHTML = `
    <div class="sobol-card-list">
      ${factors.slice(0, 6).map((item) => {
        const width = ((Number(item.total_order_index) || 0) / maxTotalOrder) * 100;
        return `
          <article class="sobol-card">
            <div class="sobol-card-head">
              <strong>${escapeHtml(formatFactorLabel(item.factor_label || item.factor))}</strong>
              <span>${escapeHtml(`总效应 ${formatNumber(item.total_order_index, 2)}`)}</span>
            </div>
            <div class="sobol-card-metrics">
              <span>一阶 ${escapeHtml(formatNumber(item.first_order_index, 2))}</span>
              <span>交互 ${escapeHtml(formatNumber(item.interaction_strength, 2))}</span>
            </div>
            <div class="driver-meter driver-meter-soft"><div class="driver-meter-fill" style="width:${width}%"></div></div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function buildAnalysisSummaryModel() {
  const dominantScenario = getDominantScenario();
  const scenarioLabel = dominantScenario ? formatPriorityScenario({ primary_scenario: dominantScenario }) : "诊断产物";
  const highPriority = state.triage?.high_priority_days?.[0] || null;
  const topDriver = state.diagnostics?.factor_summary?.top_driver_domains?.[0] || null;
  const topSource = getStrongestProcess("source");
  const topSink = getStrongestProcess("sink");
  const playbook = dominantScenario ? state.playbook?.scenario_response_playbook?.[dominantScenario] : null;
  const evidence = summarizeEvidence(highPriority?.evidence_summary, 2);
  return {
    scenarioLabel,
    highPriority,
    topDriver,
    topSource,
    topSink,
    playbook,
    evidence,
  };
}

export function renderAnalysisSummary() {
  if (document.body.dataset.page !== "analysis" || !hasElement("analysisLeadTitle")) {
    return;
  }

  const { scenarioLabel, highPriority, topDriver, topSource, topSink, playbook, evidence } = buildAnalysisSummaryModel();

  setText("analysisFocusChip", highPriority ? `${scenarioLabel} · ${formatRiskBandLabel(highPriority.risk_band)}` : scenarioLabel);
  setText("analysisLeadTitle", topDriver ? formatDomainLabel(topDriver.domain, topDriver.domain_label) : "");
  setText("analysisLeadText", "");

  setHtml(
    "analysisHeroStats",
    [
      { label: "当前分诊", value: scenarioLabel },
      { label: "转折概率", value: highPriority ? formatNumber(highPriority.predicted_critical_transition_prob, 2) : "N/A" },
      { label: "最强来源", value: topSource?.process_label || "N/A" },
      { label: "最强缓冲", value: topSink?.process_label || "N/A" },
    ].map((item) => `<article class="stat-card"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></article>`).join("")
  );

  setHtml(
    "analysisActionCards",
    `
      <article class="analysis-action-card">
        <span>事件</span>
        <strong>${escapeHtml(highPriority ? formatPriorityDate(highPriority.target_date) : "—")}</strong>
        <p>${escapeHtml(evidence.visibleFacts[0] || "")}</p>
      </article>
      <article class="analysis-action-card">
        <span>机制</span>
        <strong>${escapeHtml(topDriver ? formatDomainLabel(topDriver.domain, topDriver.domain_label) : "—")}</strong>
        <p>${escapeHtml(evidence.visibleFacts[1] || "")}</p>
      </article>
      <article class="analysis-action-card">
        <span>动作</span>
        <strong>${escapeHtml(playbook?.response_focus || "—")}</strong>
        <p>${escapeHtml(playbook?.recommended_actions?.[0] || "")}</p>
      </article>
    `
  );
}

export function setActiveAnalysisTab(tabName = ANALYSIS_DEFAULT_TAB) {
  const normalizedTab = ["diagnosis", "thresholds", "response"].includes(tabName)
    ? tabName
    : ANALYSIS_DEFAULT_TAB;
  document.querySelectorAll("[data-analysis-tab]").forEach((button) => {
    const isActive = button.dataset.analysisTab === normalizedTab;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  document.querySelectorAll(".analysis-section").forEach((section) => {
    const isActive = section.id === `analysisSection-${normalizedTab}`;
    section.classList.toggle("is-active", isActive);
    section.hidden = !isActive;
  });
  const url = new URL(window.location.href);
  url.searchParams.set("tab", normalizedTab);
  window.history.replaceState({}, "", url);
}

export function initAnalysisPage() {
  if (document.body.dataset.page !== "analysis") {
    return;
  }
  document.querySelectorAll("[data-analysis-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveAnalysisTab(button.dataset.analysisTab || ANALYSIS_DEFAULT_TAB);
    });
  });
  const initialTab = new URL(window.location.href).searchParams.get("tab") || ANALYSIS_DEFAULT_TAB;
  setActiveAnalysisTab(initialTab);
}

export function renderDiagnostics() {
  if (!hasElement("driverBars") && !hasElement("processTable")) {
    return;
  }
  if (!state.diagnostics) {
    renderMutedMessage("driverBars", "诊断摘要暂不可用。");
    renderMutedMessage("processTable", "机理分解暂不可用。");
    return;
  }
  if (document.body.dataset.page === "dashboard") {
    renderDiagnosticsOverview();
    renderAnalysisSummary();
    return;
  }
  renderDiagnosticsDetailed();
  if (document.body.dataset.page === "analysis") {
    renderProcessEvidenceDetailed();
    renderAnalysisSummary();
    return;
  }
  renderTable("processTable", state.diagnostics.process_decomposition, [
    { key: "process_label", label: "过程" },
    { key: "direction", label: "方向" },
    { key: "mean_contribution", label: "均值贡献" },
    { key: "max_contribution", label: "最大贡献" },
  ]);
  renderAnalysisSummary();
}

export function renderTriage() {
  if (!hasElement("scenarioCounts") && !hasElement("priorityTable") && !hasElement("priorityFeed")) {
    return;
  }
  if (!state.triage) {
    renderMutedMessage("scenarioCounts", "场景 triage 暂不可用。");
    renderMutedMessage("priorityTable", "高优先级日期暂不可用。");
    renderMutedMessage("priorityFeed", "高优先事件暂不可用。");
    return;
  }
  setHtml(
    "scenarioCounts",
    Object.entries(state.triage.scenario_counts || {})
      .map(([key, value]) => `<span class="badge">${escapeHtml(formatPriorityScenario({ primary_scenario: key }))}: ${escapeHtml(value)}</span>`)
      .join("") || "<span class='muted'>暂无场景统计。</span>"
  );
  const priorityDays = state.triage.high_priority_days || [];
  renderDashboardPriorityFeed(priorityDays);
  if (hasElement("priorityTable")) {
    if (document.body.dataset.page === "analysis") {
      renderTriageDetailed();
    } else {
      renderTable("priorityTable", priorityDays, [
        { key: "target_date", label: "日期" },
        { key: "primary_scenario", label: "场景" },
        { key: "risk_band", label: "风险" },
        { key: "predicted_critical_transition_prob", label: "概率" },
        { key: "evidence_summary", label: "证据" },
      ]);
    }
  }
  renderAnalysisSummary();
}

export function renderThresholds() {
  if (!["thresholdSemantics", "thresholdSnapshot", "thresholdTable", "thresholdSelect"].some(hasElement)) {
    return;
  }
  if (!state.thresholds) {
    setText("thresholdSemantics", "");
    renderMutedMessage("thresholdSnapshot", "阈值摘要暂不可用。");
    renderMutedMessage("thresholdTable", "阈值结果暂不可用。");
    const thresholdSelect = getElement("thresholdSelect");
    if (thresholdSelect) {
      thresholdSelect.innerHTML = `<option value="">全部</option>`;
    }
    return;
  }
  setText("thresholdSemantics", "");
  const snapshot = state.thresholds.risk_snapshot || {};
  setHtml(
    "thresholdSnapshot",
    [
      `测试窗口 ${formatMaybeDate(snapshot.test_window_start)} 至 ${formatMaybeDate(snapshot.test_window_end)}`,
      `临界转折率 ${formatNumber(snapshot.critical_transition_rate)}`,
      `自净失效率 ${formatNumber(snapshot.self_purification_failure_rate)}`,
      `浊度突增率 ${formatNumber(snapshot.turbidity_surge_rate)}`,
    ]
      .map((item) => `<span>${escapeHtml(item)}</span>`)
      .join("")
  );
  renderTable("thresholdTable", state.thresholds.summary || [], [
    { key: "feature_label", label: "特征" },
    { key: "threshold", label: "阈值" },
    { key: "unit", label: "单位" },
    { key: "r2_gain", label: "R²" },
    { key: "response_jump", label: "跳变" },
    { key: "status", label: "状态" },
  ]);

  const nodes = state.thresholds.knowledge_graph?.threshold_nodes || [];
  state.thresholdOptions = nodes.map((node) => ({ value: node.feature, label: node.agent_label || node.feature }));
  const thresholdSelect = getElement("thresholdSelect");
  if (thresholdSelect) {
    thresholdSelect.innerHTML = `<option value="">全部</option>${state.thresholdOptions
      .map((item) => `<option value="${escapeHtml(item.value)}" ${item.value === state.currentThresholdFeature ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
      .join("")}`;
  }
  renderAnalysisSummary();
}

export function renderBoundary() {
  if (!hasElement("boundaryMetrics") && !hasElement("boundaryNotes")) {
    return;
  }
  if (!state.boundary) {
    renderMutedMessage("boundaryMetrics", "边界摘要暂不可用。");
    renderMutedMessage("boundaryNotes", "边界说明暂不可用。");
    return;
  }
  const overall = state.boundary.summary?.overall?.test || {};
  const cmfbe = state.boundary.summary?.models?.cmfbe_stgcn?.test || {};
  const mscim = state.boundary.summary?.models?.mscim?.test || {};
  setHtml(
    "boundaryMetrics",
    [
      { label: "CMFBE F1", value: formatNumber(cmfbe.f1) },
      { label: "CMFBE 准确率", value: formatNumber(cmfbe.accuracy) },
      { label: "MSCIM F1", value: formatNumber(mscim.f1) },
      { label: "正样本", value: formatNumber(overall.positive_rate) },
    ]
      .map((item) => `<article class="stat-card"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></article>`)
      .join("")
  );
  setHtml("boundaryNotes", `<p>${escapeHtml(`代理标签 | 样本 ${overall.labeled_samples ?? "N/A"} | 正样本 ${formatNumber(overall.positive_rate)}`)}</p>`);
  renderAnalysisSummary();
}

export function renderPlaybookAndSobol() {
  if (!hasElement("playbookCards") && !hasElement("sobolTable")) {
    return;
  }
  if (!state.playbook || !state.sensitivity) {
    renderMutedMessage("playbookCards", "playbook 暂不可用。");
    renderMutedMessage("sobolTable", "敏感性结果暂不可用。");
    return;
  }
  const playbook = state.playbook.scenario_response_playbook || {};
  setHtml(
    "playbookCards",
    Object.entries(playbook)
      .slice(0, 4)
      .map(([scenario, item]) => `
        <article class="playbook-card">
          <h3>${escapeHtml(formatPriorityScenario({ primary_scenario: scenario }))}</h3>
          <ul>${(item.recommended_actions || []).slice(0, 3).map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul>
        </article>`)
      .join("") || `<p class='muted'>暂无 playbook 条目。</p>`
  );
  if (document.body.dataset.page === "analysis") {
    renderSobolDetailed();
  } else {
    renderTable("sobolTable", state.sensitivity.sobol?.top_factors || [], [
      { key: "factor_label", label: "因子" },
      { key: "first_order_index", label: "一阶" },
      { key: "total_order_index", label: "总效应" },
      { key: "interaction_strength", label: "交互" },
    ]);
  }
  renderAnalysisSummary();
}

export function renderRealtimeValidation() {
  if (!hasElement("realtimeValidationSuccessRate") && !hasElement("realtimeValidationSimilarDay")) {
    return;
  }
  const payload = state.realtimeValidation;
  if (!payload || payload.status !== "ok") {
    setText("realtimeValidationSuccessRate", "--");
    setText("realtimeValidationSimilarDay", "--");
    setText("realtimeValidationSuccessRateNote", payload?.message || "请先运行最新数据检验脚本。");
    setText("realtimeValidationSimilarDayNote", "");
    setHtml("realtimeValidationNotes", "");
    return;
  }
  const summary = payload.summary_metrics || {};
  setText("realtimeValidationSuccessRate", summary.prediction_success_rate_label || "--");
  setText("realtimeValidationSimilarDay", summary.historical_similar_day || "--");
  setText("realtimeValidationSuccessRateNote", summary.prediction_success_rate_note || "");
  setText("realtimeValidationSimilarDayNote", summary.historical_similar_day_note || "");

  setHtml(
    "realtimeValidationNotes",
    (payload.caveats || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")
  );
}

export async function loadThresholds(jobId = state.activeJobId, feature = state.currentThresholdFeature) {
  state.currentThresholdFeature = feature;
  const params = {};
  if (feature) params.feature = feature;
  if (jobId) params.job_id = jobId;
  const result = await fetchJsonSafe("thresholds", buildApiUrl("/api/v1/thresholds", params));
  state.thresholds = result.ok ? result.data : null;
  renderThresholds();
  return result;
}


