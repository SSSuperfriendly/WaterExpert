import {
  DEFAULT_MODELS,
  escapeHtml,
  formatMaybeDate,
  formatNumber,
  getElement,
  hasElement,
  hideChartTooltip,
  setHtml,
  showChartTooltip,
  state,
} from "./base.js";

const MODEL_LABELS = {
  cmfbe_stgcn: "CMFBE-ST-GCN（机制感知，推荐）",
  mscim: "MSCIM（主预测模型）",
  mscim_no_kg: "MSCIM-NoKG（无知识图谱消融）",
  persistence_baseline: "Persistence Baseline（持久性基线）",
  ridge_window_baseline: "Ridge Window Baseline（窗口回归基线）",
};

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
  const options = models
    .map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(MODEL_LABELS[model] || model)}</option>`)
    .join("");
  if (modelSelect) {
    modelSelect.innerHTML = options;
    modelSelect.value = state.predictions?.selected_model || models[0];
  }
  if (jobModelName) {
    jobModelName.innerHTML = options;
    jobModelName.value = state.predictions?.selected_model || models[0];
  }
}

function attachTooltipHandlers(svg, points) {
  svg.querySelectorAll("[data-point-index]").forEach((node) => {
    const index = Number(node.getAttribute("data-point-index"));
    const point = points[index];
    if (!point) {
      return;
    }
    node.addEventListener("mouseenter", (event) => {
      showChartTooltip(
        `
          <strong>${escapeHtml(formatMaybeDate(point.target_date))}</strong><br>
          实测浊度：${escapeHtml(formatNumber(point.actual_turbidity, 2))}<br>
          预测浊度：${escapeHtml(formatNumber(point.predicted_turbidity, 2))}<br>
          临界转折概率：${escapeHtml(formatNumber(point.predicted_critical_transition_prob, 2))}
        `,
        event.clientX,
        event.clientY
      );
    });
    node.addEventListener("mousemove", (event) => {
      showChartTooltip(
        `
          <strong>${escapeHtml(formatMaybeDate(point.target_date))}</strong><br>
          实测浊度：${escapeHtml(formatNumber(point.actual_turbidity, 2))}<br>
          预测浊度：${escapeHtml(formatNumber(point.predicted_turbidity, 2))}<br>
          临界转折概率：${escapeHtml(formatNumber(point.predicted_critical_transition_prob, 2))}
        `,
        event.clientX,
        event.clientY
      );
    });
    node.addEventListener("mouseleave", hideChartTooltip);
  });
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

  const numericRows = rows.filter((row) =>
    [row.actual_turbidity, row.predicted_turbidity].some((value) => Number.isFinite(Number(value)))
  );
  if (!numericRows.length) {
    drawChartPlaceholder("预测序列缺少有效数值，已跳过图表绘制。");
    setHtml("predictionSummary", `<span>${escapeHtml("预测序列存在空值或非数值。")}</span>`);
    return;
  }

  const svg = getElement("predictionChart");
  const width = 960;
  const height = 360;
  const padding = { top: 24, right: 32, bottom: 42, left: 50 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const turbidityValues = numericRows
    .flatMap((row) => [Number(row.actual_turbidity), Number(row.predicted_turbidity)])
    .filter(Number.isFinite);
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
  const makePath = (values, fn) =>
    values.map((value, index) => `${index === 0 ? "M" : "L"} ${padding.left + index * xStep} ${fn(value)}`).join(" ");

  const actualValues = numericRows.map((row) => Number(row.actual_turbidity) || 0);
  const predictedValues = numericRows.map((row) => Number(row.predicted_turbidity) || 0);

  const actualPath = makePath(actualValues, scaleY);
  const predictedPath = makePath(predictedValues, scaleY);
  const riskPath = makePath(riskValues, scaleRiskY);

  const gridLines = [0.2, 0.4, 0.6, 0.8]
    .map((ratio) => {
      const y = padding.top + innerHeight * ratio;
      return `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="rgba(83,102,119,0.14)" stroke-dasharray="4 6" />`;
    })
    .join("");

  const labelCount = Math.min(6, numericRows.length);
  const labelIndexes = Array.from({ length: labelCount }, (_, index) =>
    Math.round((index * (numericRows.length - 1)) / Math.max(labelCount - 1, 1))
  ).filter((value, index, array) => array.indexOf(value) === index);
  const xLabels = labelIndexes
    .map((idx) => {
      const x = padding.left + idx * xStep;
      return `<text x="${x}" y="${height - 10}" text-anchor="middle" fill="#536677" font-size="12">${escapeHtml(formatMaybeDate(numericRows[idx].target_date))}</text>`;
    })
    .join("");

  const hoverTargets = numericRows
    .map((row, index) => {
      const x = padding.left + index * xStep;
      const actualY = scaleY(Number(row.actual_turbidity) || 0);
      const predictedY = scaleY(Number(row.predicted_turbidity) || 0);
      return `
        <g data-point-index="${index}">
          <line x1="${x}" y1="${padding.top}" x2="${x}" y2="${height - padding.bottom}" stroke="rgba(83,102,119,0.08)" />
          <circle cx="${x}" cy="${actualY}" r="3.5" fill="var(--actual)" />
          <rect x="${x - 4}" y="${predictedY - 4}" width="8" height="8" rx="2" fill="var(--predicted)" />
          <circle cx="${x}" cy="${scaleRiskY(riskValues[index])}" r="2.5" fill="var(--risk)" />
          <rect x="${x - Math.max(10, xStep / 2)}" y="${padding.top}" width="${Math.max(20, xStep)}" height="${innerHeight}" fill="transparent" />
        </g>
      `;
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
    ${hoverTargets}
    ${xLabels}
  `;
  attachTooltipHandlers(svg, numericRows);

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
