import {
  DEFAULT_MODELS,
  escapeHtml,
  formatMaybeDate,
  formatNumber,
  getElement,
  hasElement,
  setHtml,
  state,
} from "./base.js";

function drawChartPlaceholder(message) {
  const svg = getElement("predictionChart");
  if (!svg) {
    return;
  }
  svg.innerHTML = `
    <rect x="0" y="0" width="960" height="360" rx="18" fill="rgba(255,255,255,0.48)"></rect>
    <text x="480" y="180" text-anchor="middle" fill="#536677" font-size="18">${escapeHtml(message)}</text>
  `;
}

export function renderPredictionControls() {
  const models = state.predictions?.available_models || DEFAULT_MODELS;
  const modelSelect = getElement("modelSelect");
  const jobModelName = getElement("jobModelName");
  if (modelSelect) {
    modelSelect.innerHTML = models
      .map((model) => `<option value="${escapeHtml(model)}" ${model === state.predictions?.selected_model ? "selected" : ""}>${escapeHtml(model)}</option>`)
      .join("");
  }
  if (jobModelName) {
    jobModelName.innerHTML = models
      .map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`)
      .join("");
  }
}

export function renderPredictionChart() {
  if (!hasElement("predictionChart")) {
    return;
  }
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

  const svg = getElement("predictionChart");
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
      `浊度 R² ${formatNumber(summary.turbidity_r2)}`,
      `浊度 RMSE ${formatNumber(summary.turbidity_rmse)}`,
      `清澈度 R² ${formatNumber(summary.clearness_r2)}`,
      `临界转折平均概率 ${formatNumber(summary.critical_transition?.mean_predicted_probability)}`,
    ]
      .map((item) => `<span>${escapeHtml(item)}</span>`)
      .join("")
  );
}
