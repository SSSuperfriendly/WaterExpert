import {
  PRIORITY_FEED_PREVIEW_COUNT,
  buildDriverLeadTitle,
  escapeHtml,
  formatDomainLabel,
  formatDomainNarrative,
  formatNumber,
  formatPriorityDate,
  formatPriorityScenario,
  formatRelativeContribution,
  formatRiskBandLabel,
  hasElement,
  maxNumeric,
  renderMutedMessage,
  setHtml,
  setText,
  state,
  summarizeEvidence,
} from "./base.js";

export function renderDiagnosticsOverview() {
  const factorSummary = state.diagnostics?.factor_summary || {};
  const driverDomains = factorSummary.top_driver_domains || [];
  const inhibitorDomains = factorSummary.top_inhibitor_domains || [];
  if (!driverDomains.length && !inhibitorDomains.length) {
    renderMutedMessage("driverBars", "风险解释暂不可用。");
    return;
  }

  const topDrivers = driverDomains.slice(0, 3);
  const stabilizers = inhibitorDomains.slice(0, 2);
  const maxDriverScore = maxNumeric(topDrivers.map((item) => item.score), 1);
  const maxStabilizerScore = maxNumeric(stabilizers.map((item) => item.score), 1);

  setHtml(
    "driverBars",
    `
      <div class="driver-overview">
        <article class="driver-lead-card">
          <div class="driver-lead-copy">
            <h3>${escapeHtml(buildDriverLeadTitle(topDrivers))}</h3>
          </div>
          <a class="text-link" href="/ui/analysis.html">详情</a>
        </article>

        <section class="driver-group">
          <div class="driver-group-head">
            <h3>推高风险</h3>
          </div>
          <div class="driver-card-list">
            ${topDrivers.map((item, index) => {
              const width = ((Number(item.score) || 0) / maxDriverScore) * 100;
              return `
                <article class="driver-card driver-card-risk">
                  <span class="driver-rank">${escapeHtml(String(index + 1).padStart(2, "0"))}</span>
                  <div class="driver-card-main">
                    <div class="driver-card-head">
                      <strong>${escapeHtml(formatDomainLabel(item.domain, item.domain_label))}</strong>
                      <span>${escapeHtml(formatRelativeContribution(item.score, maxDriverScore))}</span>
                    </div>
                    <p>${escapeHtml(formatDomainNarrative(item.domain, "driver"))}</p>
                    <div class="driver-meter"><div class="driver-meter-fill" style="width:${width}%"></div></div>
                  </div>
                </article>
              `;
            }).join("")}
          </div>
        </section>

        <section class="driver-group driver-group-soft">
          <div class="driver-group-head">
            <h3>缓解因素</h3>
          </div>
          <div class="driver-card-list driver-card-list-soft">
            ${stabilizers.length
              ? stabilizers.map((item) => {
                  const width = ((Number(item.score) || 0) / maxStabilizerScore) * 100;
                  return `
                    <article class="driver-card driver-card-soft">
                      <div class="driver-card-main">
                        <div class="driver-card-head">
                          <strong>${escapeHtml(formatDomainLabel(item.domain, item.domain_label))}</strong>
                          <span>${escapeHtml(formatRelativeContribution(item.score, maxStabilizerScore))}</span>
                        </div>
                        <p>${escapeHtml(formatDomainNarrative(item.domain, "inhibitor"))}</p>
                        <div class="driver-meter driver-meter-soft"><div class="driver-meter-fill" style="width:${width}%"></div></div>
                      </div>
                    </article>
                  `;
                }).join("")
              : ``}
          </div>
        </section>
      </div>
    `
  );
}

export function renderOverview() {
  if (!["scopeLabel", "runtimeMeta", "overviewStats", "modelBadges", "stationMeta", "guardrailsList"].some(hasElement)) {
    return;
  }
  if (!state.dashboard || !state.meta) {
    setText("scopeLabel", "");
    setText("runtimeMeta", "");
    renderMutedMessage("overviewStats", "总览信息暂不可用。");
    setHtml("modelBadges", "");
    renderMutedMessage("stationMeta", "站点摘要暂不可用。");
    return;
  }
  const dashboard = state.dashboard;
  const station = dashboard.station_profile || {};
  setText("sidebarContext", station.station_name || "吴淞口");
  setText("scopeLabel", "");
  setText("runtimeMeta", "");
  setHtml(
    "overviewStats",
    [
      { label: "最佳浊度模型", value: dashboard.best_model_summary?.best_test_turbidity_model || "N/A" },
      { label: "最佳清澈度模型", value: dashboard.best_model_summary?.best_test_clearness_model || "N/A" },
      { label: "高优先级日期数", value: (dashboard.high_priority_days || []).length },
      { label: "场景类别数", value: Object.keys(dashboard.scenario_counts || {}).length },
    ]
      .map((item) => `<article class="stat-card"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></article>`)
      .join("")
  );
  setHtml(
    "modelBadges",
    Object.entries(dashboard.test_models || {})
      .map(([name, stats]) => `<span class="badge">${escapeHtml(name)}: turbidity R² ${escapeHtml(formatNumber(stats.turbidity_r2))}</span>`)
      .join("") || "<span class='muted'>暂无模型摘要。</span>"
  );
  setHtml(
    "stationMeta",
    [
      ["站点", station.station_name],
      ["站点编号", station.station_code],
      ["河流", station.river],
      ["流域", station.basin],
      ["观测日数", station.daily_rows],
      ["建模匹配日数", station.matched_model_rows],
      ["水动力参考", station.hydrodynamic_reference_station],
      ["起始日期", station.date_start],
      ["结束日期", station.date_end],
    ]
      .map(([label, value]) => `<div class="meta-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "N/A")}</strong></div>`)
      .join("")
  );
  setHtml("guardrailsList", (dashboard.guardrails || []).map((item) => `<li>${escapeHtml(item)}</li>`).join(""));
}

export function renderDashboardPriorityFeed(priorityDays) {
  if (!hasElement("priorityFeed")) {
    return;
  }
  const previewItems = priorityDays.slice(0, PRIORITY_FEED_PREVIEW_COUNT);
  setHtml(
    "priorityFeed",
    priorityDays.length
      ? `
        <div class="priority-feed-list">
          ${previewItems.map((item) => {
            const evidence = summarizeEvidence(item.evidence_summary, 2);
            return `
          <article class="priority-card">
            <div class="priority-card-head">
              <div class="priority-topline">
                <strong class="priority-date">${escapeHtml(formatPriorityDate(item.target_date))}</strong>
                <span class="priority-prob">转折概率 ${escapeHtml(formatNumber(item.predicted_critical_transition_prob, 2))}</span>
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
          </article>
        `;
          }).join("")}
        </div>
        `
      : `<p class='muted'>暂无高优先事件。</p>`
  );
}

