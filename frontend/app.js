const DEFAULT_MODELS = ["cmfbe_stgcn", "mscim", "mscim_no_kg"];
const JOB_POLL_INTERVAL_MS = 5000;

const state = {
  meta: null,
  stations: [],
  imports: [],
  jobs: [],
  dashboard: null,
  predictions: null,
  diagnostics: null,
  triage: null,
  thresholds: null,
  boundary: null,
  playbook: null,
  sensitivity: null,
  thresholdOptions: null,
  currentThresholdFeature: "",
  activeJobId: "",
  pendingJobSelectionId: "",
  pollTimer: null,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildApiUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  return `${url.pathname}${url.search}`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return response.json();
}

async function fetchJsonSafe(label, url, options = {}) {
  try {
    return { label, ok: true, data: await fetchJson(url, options) };
  } catch (error) {
    return { label, ok: false, error: error.message };
  }
}

function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  return Number(value).toFixed(digits);
}

function formatMaybeDate(value) {
  if (!value) return "N/A";
  return String(value).slice(0, 10);
}

function setHtml(id, html) {
  document.getElementById(id).innerHTML = html;
}

function renderMutedMessage(id, message) {
  setHtml(id, `<p class='muted'>${escapeHtml(message)}</p>`);
}

function flash(message, type = "success") {
  const banner = document.getElementById("statusBanner");
  banner.textContent = message;
  banner.className = `status-banner ${type}`;
}

function summarizeIssues(issues, successMessage) {
  if (!issues.length) {
    flash(successMessage, "success");
    return;
  }
  const preview = issues.slice(0, 3).map((item) => `${item.label}: ${item.error}`).join(" | ");
  flash(`部分模块加载失败，已降级显示。${preview}`, "warning");
}

function renderTable(targetId, rows, columns, emptyMessage = "暂无数据。") {
  const container = document.getElementById(targetId);
  if (!rows || !rows.length) {
    container.innerHTML = `<p class='muted'>${escapeHtml(emptyMessage)}</p>`;
    return;
  }
  const thead = `<thead><tr>${columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${rows
    .map((row) => `<tr>${columns.map((col) => `<td>${escapeHtml(row[col.key] ?? "")}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;
  container.innerHTML = `<table class="data-table">${thead}${tbody}</table>`;
}

function drawChartPlaceholder(message) {
  const svg = document.getElementById("predictionChart");
  svg.innerHTML = `
    <rect x="0" y="0" width="960" height="360" rx="18" fill="rgba(255,255,255,0.48)"></rect>
    <text x="480" y="180" text-anchor="middle" fill="#536677" font-size="18">${escapeHtml(message)}</text>
  `;
}

function populateStationInputs() {
  const stations = state.stations || [];
  const options = stations.length
    ? stations
        .map(
          (station) =>
            `<option value="${escapeHtml(station.station_code)}">${escapeHtml(station.station_code)} - ${escapeHtml(station.station_name)}</option>`
        )
        .join("")
    : `<option value="2586">2586 - Wusongkou</option>`;
  document.getElementById("importStationCode").innerHTML = options;
  document.getElementById("jobStationCode").innerHTML = options;
}

function populateJobScopeSelector() {
  const selector = document.getElementById("jobViewSelect");
  const jobs = state.jobs || [];
  const completed = jobs.filter((job) => job.status === "completed");
  const allowedIds = new Set(completed.map((job) => job.job_id));
  if (state.activeJobId && !allowedIds.has(state.activeJobId)) {
    state.activeJobId = "";
  }
  const options = [
    `<option value="" ${state.activeJobId ? "" : "selected"}>当前内置基线产物</option>`,
    ...jobs.map((job) => {
      const disabled = job.status !== "completed" ? "disabled" : "";
      const selected = job.job_id === state.activeJobId ? "selected" : "";
      const label = `${job.job_id} | ${job.model_name || "unknown"} | ${job.status}`;
      return `<option value="${escapeHtml(job.job_id)}" ${selected} ${disabled}>${escapeHtml(label)}</option>`;
    }),
  ];
  selector.innerHTML = options.join("");
}

function renderOverview() {
  if (!state.dashboard || !state.meta) {
    document.getElementById("scopeLabel").textContent = "部分数据不可用";
    document.getElementById("runtimeMeta").textContent = state.meta
      ? `内部算法运行时: ${state.meta.runtime_root}`
      : "内部算法运行时信息暂不可用。";
    renderMutedMessage("overviewStats", "总览信息暂不可用。");
    setHtml("modelBadges", "");
    renderMutedMessage("stationMeta", "站点摘要暂不可用。");
    return;
  }
  const dashboard = state.dashboard;
  const station = dashboard.station_profile || {};
  document.getElementById("scopeLabel").textContent = dashboard.prototype_scope || "N/A";
  document.getElementById("runtimeMeta").textContent = `内部算法运行时: ${state.meta.runtime_root} | 产物范围: ${state.meta.artifact_scope || "integrated-default"} | 产物根: ${state.meta.outputs_root || "N/A"}`;
  setHtml(
    "overviewStats",
    [
      { label: "最佳浊度模型", value: dashboard.best_model_summary?.best_test_turbidity_model || "N/A" },
      { label: "最佳清澈度模型", value: dashboard.best_model_summary?.best_test_clearness_model || "N/A" },
      { label: "高优先级日期数", value: (dashboard.high_priority_days || []).length },
      { label: "场景类别数", value: Object.keys(dashboard.scenario_counts || {}).length },
    ]
      .map(
        (item) => `<article class="stat-card"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></article>`
      )
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

function renderImports() {
  renderTable("importsTable", state.imports, [
    { key: "created_at", label: "创建时间" },
    { key: "data_type", label: "数据类型" },
    { key: "source_name", label: "来源名称" },
    { key: "status", label: "状态" },
    { key: "rows_detected", label: "检测行数" },
    { key: "stored_path", label: "内部存储路径" },
    { key: "message", label: "消息" },
  ]);
}

function renderJobs() {
  renderTable("jobsTable", state.jobs, [
    { key: "created_at", label: "创建时间" },
    { key: "mode", label: "模式" },
    { key: "model_name", label: "模型" },
    { key: "status", label: "状态" },
    { key: "use_existing_artifacts", label: "复用现有产物" },
    { key: "artifact_root", label: "任务产物目录" },
    { key: "finished_at", label: "完成时间" },
    { key: "message", label: "消息" },
  ], "当前没有任务记录。");
  populateJobScopeSelector();
}

function renderPredictionControls() {
  const models = state.predictions?.available_models || DEFAULT_MODELS;
  document.getElementById("modelSelect").innerHTML = models
    .map((model) => `<option value="${escapeHtml(model)}" ${model === state.predictions?.selected_model ? "selected" : ""}>${escapeHtml(model)}</option>`)
    .join("");
  document.getElementById("jobModelName").innerHTML = models
    .map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`)
    .join("");
}

function renderPredictionChart() {
  const rows = state.predictions?.series || [];
  if (!rows.length) {
    drawChartPlaceholder("当前没有可绘制的预测序列。");
    setHtml("predictionSummary", `<span>${escapeHtml("暂无预测摘要。")}</span>`);
    return;
  }

  const numericRows = rows.filter((row) => [row.actual_turbidity, row.predicted_turbidity].some((value) => Number.isFinite(Number(value))));
  if (!numericRows.length) {
    drawChartPlaceholder("预测序列缺少有效数值，已跳过绘图。");
    setHtml("predictionSummary", `<span>${escapeHtml("预测序列存在空值或非数值。")}</span>`);
    return;
  }

  const svg = document.getElementById("predictionChart");
  const width = 960;
  const height = 360;
  const padding = { top: 24, right: 32, bottom: 38, left: 50 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const turbidityValues = numericRows
    .flatMap((row) => [Number(row.actual_turbidity), Number(row.predicted_turbidity)])
    .filter((value) => Number.isFinite(value));
  if (!turbidityValues.length) {
    drawChartPlaceholder("浊度序列为空，无法生成图表。");
    return;
  }
  const riskValues = numericRows.map((row) => {
    const value = Number(row.predicted_critical_transition_prob);
    return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  });
  const yMin = Math.min(...turbidityValues);
  const yMax = Math.max(...turbidityValues);
  const xStep = innerWidth / Math.max(numericRows.length - 1, 1);
  const scaleY = (value) => {
    const ratio = (value - yMin) / Math.max(yMax - yMin, 1e-6);
    return padding.top + innerHeight - ratio * innerHeight;
  };
  const scaleRiskY = (value) => padding.top + innerHeight - value * innerHeight;

  const makePath = (values, fn) => values
    .map((value, index) => `${index === 0 ? "M" : "L"} ${padding.left + index * xStep} ${fn(value)}`)
    .join(" ");

  const actualPath = makePath(numericRows.map((row) => Number(row.actual_turbidity) || 0), scaleY);
  const predictedPath = makePath(numericRows.map((row) => Number(row.predicted_turbidity) || 0), scaleY);
  const riskPath = makePath(riskValues, scaleRiskY);

  const gridLines = [0.25, 0.5, 0.75]
    .map((ratio) => {
      const y = padding.top + innerHeight * ratio;
      return `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="rgba(83,102,119,0.14)" stroke-dasharray="4 6" />`;
    })
    .join("");

  const xLabels = [0, Math.floor(numericRows.length / 2), numericRows.length - 1]
    .filter((value, index, array) => array.indexOf(value) === index)
    .map((idx) => {
      const x = padding.left + idx * xStep;
      return `<text x="${x}" y="${height - 10}" text-anchor="middle" fill="#536677" font-size="12">${escapeHtml(formatMaybeDate(numericRows[idx].target_date))}</text>`;
    })
    .join("");

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
    ${gridLines}
    <path d="${actualPath}" fill="none" stroke="var(--actual)" stroke-width="3.2" stroke-linejoin="round"></path>
    <path d="${predictedPath}" fill="none" stroke="var(--predicted)" stroke-width="3.2" stroke-linejoin="round"></path>
    <path d="${riskPath}" fill="none" stroke="var(--risk)" stroke-width="2.4" stroke-dasharray="8 6"></path>
    <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(83,102,119,0.24)" />
    <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(83,102,119,0.24)" />
    ${xLabels}
  `;

  const summary = state.predictions?.summary || {};
  setHtml(
    "predictionSummary",
    [
      `Turbidity R² ${formatNumber(summary.turbidity_r2)}`,
      `Turbidity RMSE ${formatNumber(summary.turbidity_rmse)}`,
      `Clearness R² ${formatNumber(summary.clearness_r2)}`,
      `Critical transition mean prob ${formatNumber(summary.critical_transition?.mean_predicted_probability)}`,
    ]
      .map((item) => `<span>${escapeHtml(item)}</span>`)
      .join("")
  );
}

function renderDiagnostics() {
  if (!state.diagnostics) {
    renderMutedMessage("driverBars", "诊断摘要暂不可用。");
    renderMutedMessage("processTable", "机理分解暂不可用。");
    return;
  }
  const drivers = state.diagnostics.factor_summary?.top_driver_features || [];
  const maxScore = Math.max(...drivers.map((item) => Number(item.driver_score) || 0), 1);
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
  renderTable("processTable", state.diagnostics.process_decomposition, [
    { key: "process_label", label: "过程" },
    { key: "direction", label: "方向" },
    { key: "mean_contribution", label: "均值贡献" },
    { key: "max_contribution", label: "最大贡献" },
  ]);
}

function renderTriage() {
  if (!state.triage) {
    renderMutedMessage("scenarioCounts", "场景 triage 暂不可用。");
    renderMutedMessage("priorityTable", "高优先级日期暂不可用。");
    return;
  }
  setHtml(
    "scenarioCounts",
    Object.entries(state.triage.scenario_counts || {})
      .map(([key, value]) => `<span class="badge">${escapeHtml(key)}: ${escapeHtml(value)}</span>`)
      .join("") || "<span class='muted'>暂无场景统计。</span>"
  );
  renderTable("priorityTable", state.triage.high_priority_days || [], [
    { key: "target_date", label: "日期" },
    { key: "primary_scenario", label: "主场景" },
    { key: "risk_band", label: "风险带" },
    { key: "predicted_critical_transition_prob", label: "临界转折概率" },
    { key: "evidence_summary", label: "证据摘要" },
  ]);
}

function renderThresholds() {
  if (!state.thresholds) {
    document.getElementById("thresholdSemantics").textContent = "";
    renderMutedMessage("thresholdSnapshot", "阈值摘要暂不可用。");
    renderMutedMessage("thresholdTable", "阈值结果暂不可用。");
    document.getElementById("thresholdSelect").innerHTML = `<option value="">全部</option>`;
    return;
  }
  document.getElementById("thresholdSemantics").textContent = state.thresholds.threshold_semantics || "";
  const snapshot = state.thresholds.risk_snapshot || {};
  setHtml(
    "thresholdSnapshot",
    [
      `Test window ${formatMaybeDate(snapshot.test_window_start)} to ${formatMaybeDate(snapshot.test_window_end)}`,
      `Critical transition rate ${formatNumber(snapshot.critical_transition_rate)}`,
      `Self-purification failure rate ${formatNumber(snapshot.self_purification_failure_rate)}`,
      `Turbidity surge rate ${formatNumber(snapshot.turbidity_surge_rate)}`,
    ]
      .map((item) => `<span>${escapeHtml(item)}</span>`)
      .join("")
  );
  renderTable("thresholdTable", state.thresholds.summary || [], [
    { key: "feature_label", label: "特征" },
    { key: "threshold", label: "阈值" },
    { key: "unit", label: "单位" },
    { key: "r2_gain", label: "R² 增益" },
    { key: "response_jump", label: "响应跳变" },
    { key: "status", label: "状态" },
  ]);

  const nodes = state.thresholds.knowledge_graph?.threshold_nodes || [];
  state.thresholdOptions = nodes.map((node) => ({ value: node.feature, label: node.agent_label || node.feature }));
  document.getElementById("thresholdSelect").innerHTML = `<option value="">全部</option>${state.thresholdOptions
    .map((item) => `<option value="${escapeHtml(item.value)}" ${item.value === state.currentThresholdFeature ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("")}`;
}

function renderBoundary() {
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
      { label: "CMFBE Test F1", value: formatNumber(cmfbe.f1) },
      { label: "CMFBE Test Accuracy", value: formatNumber(cmfbe.accuracy) },
      { label: "MSCIM Test F1", value: formatNumber(mscim.f1) },
      { label: "Positive Rate", value: formatNumber(overall.positive_rate) },
    ]
      .map((item) => `<article class="stat-card"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></article>`)
      .join("")
  );
  setHtml(
    "boundaryNotes",
    `<strong>${escapeHtml("Label note")}</strong><p>${escapeHtml(`当前边界监督来自 raster 派生代理标签；测试集标注样本数为 ${overall.labeled_samples ?? "N/A"}，正样本比例为 ${formatNumber(overall.positive_rate)}。请不要把该摘要解读成已验证的空间治理边界产品。`)}</p>`
  );
}

function renderPlaybookAndSobol() {
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
          <h3>${escapeHtml(scenario)}</h3>
          <p>${escapeHtml(item.response_focus || "")}</p>
          <ul>${(item.recommended_actions || []).map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul>
        </article>`)
      .join("") || `<p class='muted'>暂无 playbook 条目。</p>`
  );
  renderTable("sobolTable", state.sensitivity.sobol?.top_factors || [], [
    { key: "factor_label", label: "因子" },
    { key: "first_order_index", label: "一阶指数" },
    { key: "total_order_index", label: "总效应指数" },
    { key: "interaction_strength", label: "交互强度" },
  ]);
}

async function loadPredictions(model = null, jobId = state.activeJobId) {
  const params = { split: "test" };
  if (model) params.model = model;
  if (jobId) params.job_id = jobId;
  const result = await fetchJsonSafe("predictions", buildApiUrl("/api/v1/predictions", params));
  state.predictions = result.ok ? result.data : null;
  renderPredictionControls();
  renderPredictionChart();
  return result;
}

async function loadThresholds(feature = "", jobId = state.activeJobId) {
  state.currentThresholdFeature = feature;
  const params = {};
  if (feature) params.feature = feature;
  if (jobId) params.job_id = jobId;
  const result = await fetchJsonSafe("thresholds", buildApiUrl("/api/v1/thresholds", params));
  state.thresholds = result.ok ? result.data : null;
  renderThresholds();
  return result;
}

async function refreshOperationalData({ silent = false } = {}) {
  const [importsResult, jobsResult] = await Promise.all([
    fetchJsonSafe("imports", "/api/v1/data/imports"),
    fetchJsonSafe("jobs", "/api/v1/prediction-jobs"),
  ]);
  state.imports = importsResult.ok ? importsResult.data : [];
  state.jobs = jobsResult.ok ? jobsResult.data : [];
  renderImports();
  renderJobs();
  scheduleJobPolling();
  const issues = [importsResult, jobsResult].filter((item) => !item.ok);
  if (!silent && issues.length) {
    summarizeIssues(issues, "操作数据已刷新。");
  }
  return issues;
}

async function loadStaticData() {
  const [stationsResult] = await Promise.all([
    fetchJsonSafe("stations", "/api/v1/stations"),
  ]);
  state.stations = stationsResult.ok ? stationsResult.data : [];
  populateStationInputs();
  return [stationsResult].filter((item) => !item.ok);
}

async function loadArtifactData(jobId = state.activeJobId, { silent = false } = {}) {
  const params = jobId ? { job_id: jobId } : {};
  const [metaResult, dashboardResult, diagnosticsResult, triageResult, boundaryResult, playbookResult, sensitivityResult] = await Promise.all([
    fetchJsonSafe("meta", buildApiUrl("/api/v1/meta", params)),
    fetchJsonSafe("dashboard", buildApiUrl("/api/v1/dashboard", params)),
    fetchJsonSafe("diagnostics", buildApiUrl("/api/v1/diagnostics", params)),
    fetchJsonSafe("scenario-triage", buildApiUrl("/api/v1/scenario-triage", params)),
    fetchJsonSafe("boundary", buildApiUrl("/api/v1/boundary", params)),
    fetchJsonSafe("response-playbook", buildApiUrl("/api/v1/response-playbook", params)),
    fetchJsonSafe("sensitivity", buildApiUrl("/api/v1/sensitivity", params)),
  ]);

  state.meta = metaResult.ok ? metaResult.data : null;
  state.dashboard = dashboardResult.ok ? dashboardResult.data : null;
  state.diagnostics = diagnosticsResult.ok ? diagnosticsResult.data : null;
  state.triage = triageResult.ok ? triageResult.data : null;
  state.boundary = boundaryResult.ok ? boundaryResult.data : null;
  state.playbook = playbookResult.ok ? playbookResult.data : null;
  state.sensitivity = sensitivityResult.ok ? sensitivityResult.data : null;

  const predictionResult = await loadPredictions(null, jobId);
  const thresholdResult = await loadThresholds(state.currentThresholdFeature, jobId);

  renderOverview();
  renderDiagnostics();
  renderTriage();
  renderBoundary();
  renderPlaybookAndSobol();

  const issues = [
    metaResult,
    dashboardResult,
    diagnosticsResult,
    triageResult,
    boundaryResult,
    playbookResult,
    sensitivityResult,
    predictionResult,
    thresholdResult,
  ].filter((item) => !item.ok);
  if (!silent) {
    summarizeIssues(issues, jobId ? `已切换到任务产物视图: ${jobId}` : "系统已加载集成运行时与当前产品状态。");
  }
  return issues;
}

async function loadAll({ silent = false } = {}) {
  const staticIssues = await loadStaticData();
  const operationalIssues = await refreshOperationalData({ silent: true });
  const artifactIssues = await loadArtifactData(state.activeJobId, { silent: true });
  const issues = [...staticIssues, ...operationalIssues, ...artifactIssues];
  if (!silent) {
    summarizeIssues(issues, state.activeJobId ? `已刷新任务产物视图: ${state.activeJobId}` : "系统已加载集成运行时与当前产品状态。");
  }
}

async function exportReport() {
  const url = buildApiUrl("/api/v1/report/export", state.activeJobId ? { job_id: state.activeJobId } : {});
  const payload = await fetchJson(url, { method: "POST" });
  flash(`报告已导出: ${payload.report_path}`);
  window.open(payload.download_url, "_blank", "noopener");
}

async function handleImportSubmit(event) {
  event.preventDefault();
  const payload = {
    data_type: document.getElementById("importDataType").value,
    source_name: document.getElementById("importSourceName").value,
    file_path: document.getElementById("importFilePath").value,
    time_granularity: document.getElementById("importGranularity").value,
    station_code: document.getElementById("importStationCode").value,
  };
  const result = await fetchJson("/api/v1/data/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  flash(`数据导入记录已创建: ${result.status}`);
  document.getElementById("importForm").reset();
  document.getElementById("importGranularity").value = "daily";
  populateStationInputs();
  await refreshOperationalData({ silent: true });
}

async function handleJobSubmit(event) {
  event.preventDefault();
  const payload = {
    mode: document.getElementById("jobMode").value,
    model_name: document.getElementById("jobModelName").value,
    station_code: document.getElementById("jobStationCode").value,
    start_date: document.getElementById("jobStartDate").value || null,
    end_date: document.getElementById("jobEndDate").value || null,
    use_existing_artifacts: document.getElementById("jobUseExisting").checked,
  };
  const result = await fetchJson("/api/v1/prediction-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshOperationalData({ silent: true });
  if (payload.use_existing_artifacts) {
    state.activeJobId = result.job_id;
    await loadArtifactData(state.activeJobId, { silent: true });
    flash(`预测任务已创建并已切换到任务产物视图: ${result.job_id}`);
  } else {
    state.pendingJobSelectionId = result.job_id;
    flash(`预测任务已创建: ${result.job_id} (${result.status})，系统将自动轮询直到完成。`);
  }
}

function stopJobPolling() {
  if (state.pollTimer) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function scheduleJobPolling() {
  stopJobPolling();
  if ((state.jobs || []).some((job) => job.status === "running")) {
    state.pollTimer = window.setTimeout(pollJobs, JOB_POLL_INTERVAL_MS);
  }
}

async function pollJobs() {
  const previousStatuses = new Map((state.jobs || []).map((job) => [job.job_id, job.status]));
  await refreshOperationalData({ silent: true });

  if (state.pendingJobSelectionId) {
    const pending = (state.jobs || []).find((job) => job.job_id === state.pendingJobSelectionId);
    if (pending?.status === "completed") {
      state.activeJobId = pending.job_id;
      state.pendingJobSelectionId = "";
      await loadArtifactData(state.activeJobId, { silent: true });
      flash(`预测任务已完成，已切换到任务产物视图: ${pending.job_id}`);
    } else if (pending && ["failed", "orphaned"].includes(pending.status)) {
      state.pendingJobSelectionId = "";
      flash(`预测任务结束于异常状态: ${pending.job_id} (${pending.status})`, "error");
    }
  }

  if (state.activeJobId) {
    const current = (state.jobs || []).find((job) => job.job_id === state.activeJobId);
    const previous = previousStatuses.get(state.activeJobId);
    if (current?.status === "completed" && previous === "running") {
      await loadArtifactData(state.activeJobId, { silent: true });
      flash(`当前查看任务已完成并刷新产物: ${state.activeJobId}`);
    }
    if (current && ["failed", "orphaned"].includes(current.status) && previous === "running") {
      flash(`当前查看任务进入异常状态: ${current.job_id} (${current.status})`, "error");
    }
  }

  scheduleJobPolling();
}

document.getElementById("refreshButton").addEventListener("click", async () => {
  try {
    await loadAll();
  } catch (error) {
    flash(`刷新失败: ${error.message}`, "error");
  }
});

document.getElementById("exportReportButton").addEventListener("click", async () => {
  try {
    await exportReport();
  } catch (error) {
    flash(`导出失败: ${error.message}`, "error");
  }
});

document.getElementById("importForm").addEventListener("submit", async (event) => {
  try {
    await handleImportSubmit(event);
  } catch (error) {
    flash(`导入失败: ${error.message}`, "error");
  }
});

document.getElementById("jobForm").addEventListener("submit", async (event) => {
  try {
    await handleJobSubmit(event);
  } catch (error) {
    flash(`任务创建失败: ${error.message}`, "error");
  }
});

document.getElementById("modelSelect").addEventListener("change", async (event) => {
  try {
    const result = await loadPredictions(event.target.value, state.activeJobId);
    summarizeIssues(result.ok ? [] : [result], "模型切换成功。");
  } catch (error) {
    flash(`模型切换失败: ${error.message}`, "error");
  }
});

document.getElementById("thresholdSelect").addEventListener("change", async (event) => {
  try {
    const result = await loadThresholds(event.target.value, state.activeJobId);
    summarizeIssues(result.ok ? [] : [result], "阈值加载成功。");
  } catch (error) {
    flash(`阈值加载失败: ${error.message}`, "error");
  }
});

document.getElementById("jobViewSelect").addEventListener("change", async (event) => {
  try {
    state.activeJobId = event.target.value;
    await loadArtifactData(state.activeJobId, { silent: false });
  } catch (error) {
    flash(`任务产物切换失败: ${error.message}`, "error");
  }
});

loadAll()
  .catch((error) => {
    console.error(error);
    flash(`加载失败: ${error.message}`, "error");
  });
