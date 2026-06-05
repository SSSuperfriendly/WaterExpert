export const DEFAULT_MODELS = ["cmfbe_stgcn", "mscim", "mscim_no_kg"];
export const JOB_POLL_INTERVAL_MS = 5000;
export const SIDEBAR_BREAKPOINT_PX = 960;
export const SIDEBAR_COLLAPSED_KEY = "waterexpert.sidebar.collapsed";
export const SIDEBAR_WIDTH_KEY = "waterexpert.sidebar.width";
export const SIDEBAR_WIDTH_MIN_PX = 220;
export const SIDEBAR_WIDTH_MAX_PX = 420;
export const SIDEBAR_DRAG_THRESHOLD_PX = 6;
export const PRIORITY_FEED_PREVIEW_COUNT = 3;
export const ANALYSIS_DEFAULT_TAB = "diagnosis";
export const THEME_STORAGE_KEY = "waterexpert.theme";
export const REPORT_EXPORT_FORMATS = {
  html: { label: "HTML", extension: ".html", mime: "text/html" },
  md: { label: "Markdown", extension: ".md", mime: "text/markdown" },
  json: { label: "JSON", extension: ".json", mime: "application/json" },
  pdf: { label: "PDF", extension: ".pdf", mime: "application/pdf" },
};

export const state = {
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

export function getElement(id) {
  return document.getElementById(id);
}

export function hasElement(id) {
  return Boolean(getElement(id));
}

export function getValue(id, fallback = "") {
  const element = getElement(id);
  return element ? element.value : fallback;
}

export function getChecked(id) {
  return Boolean(getElement(id)?.checked);
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function maxNumeric(values, fallback = 1) {
  const numericValues = values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  return numericValues.length ? Math.max(...numericValues) : fallback;
}

export function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  return Number(value).toFixed(digits);
}

export function formatMaybeDate(value) {
  if (!value) return "N/A";
  return String(value).slice(0, 10);
}

export function formatPriorityDate(value) {
  if (!value) {
    return "未知日期";
  }
  const parsed = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return formatMaybeDate(value);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
  }).format(parsed);
}

export function formatPriorityScenario(item) {
  const fallbackLabels = {
    external_input: "外源输入",
    internal_release: "内源释放",
    algal_dominant: "藻类主导",
    chronic_composite: "复合慢性压力",
  };
  return item.primary_scenario_label || fallbackLabels[item.primary_scenario] || item.primary_scenario || "未知场景";
}

export function formatRiskBandLabel(value) {
  const labels = {
    high: "高风险",
    heightened: "偏高风险",
    watch: "关注",
  };
  return labels[value] || value || "未标注";
}

export function formatProcessDirection(value) {
  return value === "sink" ? "缓冲过程" : "来源过程";
}

export function formatFactorLabel(value) {
  const fallbackLabels = {
    runoff_sediment_pulse: "径流泥沙脉冲",
    "runoff sediment pulse": "径流泥沙脉冲",
    songpu_flushing_potential: "松浦冲刷外输潜力",
    "Songpu flushing potential": "松浦冲刷外输潜力",
    precipitation_3d: "3日累计降雨",
    "3-day cumulative precipitation": "3日累计降雨",
    songpu_flow_m3s_abs: "松浦绝对流量",
    "Songpu absolute flow": "松浦绝对流量",
    dissolved_oxygen: "溶解氧",
    "dissolved oxygen": "溶解氧",
    huangdu_flow_m3s_abs: "黄渡绝对流量",
    "Huangdu absolute flow": "黄渡绝对流量",
    self_purification_index: "自净指数",
    "self-purification index": "自净指数",
    water_temp: "水温",
    "water temperature": "水温",
  };
  return fallbackLabels[value] || value || "未标注因子";
}

export function summarizeEvidence(summary, previewCount = 2) {
  const facts = String(summary || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
  return {
    visibleFacts: facts.slice(0, previewCount),
    hiddenCount: Math.max(facts.length - previewCount, 0),
  };
}

export function formatDomainLabel(domain, providedLabel) {
  const fallbackLabels = {
    rainfall: "降雨过程",
    flow: "水动力过程",
    wind: "风场扰动",
    runoff: "径流输入",
    sediment: "泥沙再悬浮",
    water_quality: "水质本底",
    nutrients: "营养盐负荷",
    self_purification: "自净沉降",
    agriculture: "农业面源",
  };
  return providedLabel || fallbackLabels[domain] || domain || "未标注机制";
}

export function formatDomainNarrative(domain, direction = "driver") {
  const narratives = {
    rainfall: {
      driver: "更像外部输入被快速放大，优先检查降雨与短时来水条件。",
      inhibitor: "降雨相关压力当前相对可控，没有成为主要放大项。",
    },
    flow: {
      driver: "输移与混合作用正在抬高风险，说明水动力过程参与较强。",
      inhibitor: "水动力过程对风险仍有一定缓冲，不完全是放大型信号。",
    },
    wind: {
      driver: "风场扰动可能在增强表层混合或再悬浮效应。",
      inhibitor: "风场扰动当前没有持续推高风险，作用相对受限。",
    },
    runoff: {
      driver: "径流输入正在增加负荷，偏向外源驱动型风险。",
      inhibitor: "径流输入并未持续推高压力，当前更像背景项。",
    },
    sediment: {
      driver: "再悬浮与底泥扰动正在放大浊度响应，偏向内源释放压力。",
      inhibitor: "泥沙扰动当前仍有一定受限，没有成为最强放大器。",
    },
    water_quality: {
      driver: "背景水质状态本身就在推高系统压力，不只是短时事件。",
      inhibitor: "当前水质本底对风险还有一定压制，说明背景条件不算最差。",
    },
    nutrients: {
      driver: "营养盐负荷在抬高风险，偏向慢性叠加型压力。",
      inhibitor: "营养盐相关压力仍有缓冲，不是这轮风险的主导项。",
    },
    self_purification: {
      driver: "自净支撑偏弱，系统缓冲能力不足。",
      inhibitor: "自净过程仍在发挥缓冲作用，没有完全失守。",
    },
    agriculture: {
      driver: "农业面源信号有叠加，但更像辅助放大项。",
      inhibitor: "农业面源当前不是主要风险来源，影响相对靠后。",
    },
  };
  return narratives[domain]?.[direction] || (direction === "driver" ? "当前作为风险推动因素出现。" : "当前仍在提供一定缓冲。");
}

export function formatRelativeContribution(score, maxScore) {
  const numericScore = Number(score);
  const numericMax = Number(maxScore);
  if (!Number.isFinite(numericScore) || !Number.isFinite(numericMax) || numericMax <= 0) {
    return "贡献未知";
  }
  return `相对贡献 ${Math.round((numericScore / numericMax) * 100)}%`;
}

export function buildDriverLeadTitle(driverDomains) {
  if (!driverDomains.length) {
    return "";
  }
  return formatDomainLabel(driverDomains[0].domain, driverDomains[0].domain_label);
}

export function setHtml(id, html) {
  const element = getElement(id);
  if (element) {
    element.innerHTML = html;
  }
}

export function setText(id, text) {
  const element = getElement(id);
  if (element) {
    element.textContent = text;
  }
}

export function renderMutedMessage(id, message) {
  setHtml(id, `<p class='muted'>${escapeHtml(message)}</p>`);
}

export function flash(message, type = "success") {
  const banner = getElement("statusBanner");
  if (!banner) {
    console[type === "error" ? "error" : "log"](message);
    return;
  }
  banner.textContent = message;
  banner.className = `status-banner ${type}`;
}

export function clearFlash() {
  const banner = getElement("statusBanner");
  if (!banner) {
    return;
  }
  banner.textContent = "";
  banner.className = "status-banner hidden";
}

export function showDownloadAlert(message) {
  if (typeof window.alert === "function") {
    window.alert(message);
  }
}

export function summarizeIssues(issues, successMessage) {
  if (!issues.length) {
    if (successMessage) {
      flash(successMessage, "success");
    } else {
      clearFlash();
    }
    return;
  }
  const preview = issues.slice(0, 3).map((item) => `${item.label}: ${item.error}`).join(" | ");
  flash(`部分模块加载失败，已降级显示。${preview}`, "warning");
}

export function renderTable(targetId, rows, columns, emptyMessage = "暂无数据。") {
  const container = getElement(targetId);
  if (!container) {
    return;
  }
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

export function populateStationInputs() {
  const stations = state.stations || [];
  const options = stations.length
    ? stations
        .map((station) => `<option value="${escapeHtml(station.station_code)}">${escapeHtml(station.station_code)} - ${escapeHtml(station.station_name)}</option>`)
        .join("")
    : `<option value="2586">2586 - Wusongkou</option>`;
  const importStation = getElement("importStationCode");
  const jobStation = getElement("jobStationCode");
  if (importStation) {
    importStation.innerHTML = options;
  }
  if (jobStation) {
    jobStation.innerHTML = options;
  }
}

export function populateJobScopeSelector() {
  const selector = getElement("jobViewSelect");
  if (!selector) {
    return;
  }
  const jobs = state.jobs || [];
  const completed = jobs.filter((job) => job.status === "completed");
  const allowedIds = new Set(completed.map((job) => job.job_id));
  if (state.activeJobId && !allowedIds.has(state.activeJobId)) {
    state.activeJobId = "";
  }
  const options = [
    `<option value="" ${state.activeJobId ? "" : "selected"}>基线产物</option>`,
    ...jobs.map((job) => {
      const disabled = job.status !== "completed" ? "disabled" : "";
      const selected = job.job_id === state.activeJobId ? "selected" : "";
      const label = `${job.job_id} | ${job.model_name || "unknown"} | ${job.status}`;
      return `<option value="${escapeHtml(job.job_id)}" ${selected} ${disabled}>${escapeHtml(label)}</option>`;
    }),
  ];
  selector.innerHTML = options.join("");
}

export function renderImports() {
  renderTable("importsTable", state.imports, [
    { key: "created_at", label: "时间" },
    { key: "data_type", label: "类型" },
    { key: "source_name", label: "来源" },
    { key: "status", label: "状态" },
    { key: "rows_detected", label: "行数" },
    { key: "stored_path", label: "路径" },
    { key: "message", label: "消息" },
  ]);
}

export function renderJobs() {
  renderTable("jobsTable", state.jobs, [
    { key: "created_at", label: "时间" },
    { key: "mode", label: "模式" },
    { key: "model_name", label: "模型" },
    { key: "status", label: "状态" },
    { key: "use_existing_artifacts", label: "复用" },
    { key: "artifact_root", label: "产物" },
    { key: "finished_at", label: "完成" },
    { key: "message", label: "消息" },
  ], "当前没有任务记录。");
  populateJobScopeSelector();
}

export function bindAsyncEvent(element, eventName, handler, errorPrefix) {
  if (!element) {
    return;
  }
  element.addEventListener(eventName, async (event) => {
    try {
      await handler(event);
    } catch (error) {
      flash(`${errorPrefix}: ${error.message}`, "error");
    }
  });
}
