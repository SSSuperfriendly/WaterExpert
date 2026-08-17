import { fetchJson, fetchJsonSafe } from "./api.js";
import {
  escapeHtml,
  formatMaybeDate,
  formatNumber,
  hideChartTooltip,
  renderTable,
  setHtml,
  setLoadingState,
  setText,
  showChartTooltip,
} from "./base.js";
import { initAuthenticatedShell } from "./app-shell.js";

function showStatus(message, type = "warning") {
  const banner = document.getElementById("visualStatus");
  if (!banner) {
    return;
  }
  banner.textContent = message;
  banner.className = message ? `status-banner ${type}` : "status-banner hidden";
}

function populateStations(stations) {
  const select = document.getElementById("visualStationCode");
  if (!select) {
    return;
  }
  select.innerHTML = stations
    .map(
      (station) =>
        `<option value="${escapeHtml(station.station_code)}" ${station.station_code === "2586" ? "selected" : ""}>${escapeHtml(station.station_code)} - ${escapeHtml(station.station_name)}</option>`
    )
    .join("");
}

function populateIndicators(indicators) {
  const select = document.getElementById("visualIndicator");
  if (!select) {
    return;
  }
  select.innerHTML = indicators
    .map(
      (item) =>
        `<option value="${escapeHtml(item.key)}" ${item.key === "turbidity" ? "selected" : ""}>${escapeHtml(item.label)}</option>`
    )
    .join("");
}

function attachTooltipHandlers(svg, points) {
  svg.querySelectorAll("[data-series-index]").forEach((node) => {
    const index = Number(node.getAttribute("data-series-index"));
    const point = points[index];
    if (!point) {
      return;
    }
    const tooltipHtml = `
      <strong>${escapeHtml(formatMaybeDate(point.date))}</strong><br>
      数值：${escapeHtml(formatNumber(point.value, 2))}
    `;
    node.addEventListener("mouseenter", (event) => {
      showChartTooltip(tooltipHtml, event.clientX, event.clientY);
    });
    node.addEventListener("mousemove", (event) => {
      showChartTooltip(tooltipHtml, event.clientX, event.clientY);
    });
    node.addEventListener("mouseleave", hideChartTooltip);
  });
}

function renderChart(series) {
  const svg = document.getElementById("visualChart");
  if (!svg) {
    return;
  }
  const numericSeries = series.filter((item) => Number.isFinite(Number(item.value)));
  if (!numericSeries.length) {
    svg.innerHTML = `<text x="480" y="180" text-anchor="middle">暂无可视化数据</text>`;
    return;
  }
  const values = numericSeries.map((item) => Number(item.value));
  const width = 960;
  const height = 320;
  const padding = { top: 24, right: 20, bottom: 40, left: 52 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const step = innerWidth / Math.max(numericSeries.length - 1, 1);
  const path = numericSeries
    .map((item, index) => {
      const numeric = Number(item.value);
      const ratio = (numeric - minValue) / Math.max(maxValue - minValue, 1e-6);
      const x = padding.left + index * step;
      const y = padding.top + innerHeight - ratio * innerHeight;
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  const labelCount = Math.min(6, numericSeries.length);
  const labelIndexes = Array.from({ length: labelCount }, (_, index) =>
    Math.round((index * (numericSeries.length - 1)) / Math.max(labelCount - 1, 1))
  ).filter((value, index, array) => array.indexOf(value) === index);
  const xLabels = labelIndexes
    .map((idx) => {
      const x = padding.left + idx * step;
      return `<text x="${x}" y="${height - 10}" text-anchor="middle" fill="#536677" font-size="12">${escapeHtml(formatMaybeDate(numericSeries[idx].date))}</text>`;
    })
    .join("");

  const markers = numericSeries
    .map((item, index) => {
      const numeric = Number(item.value);
      const ratio = (numeric - minValue) / Math.max(maxValue - minValue, 1e-6);
      const x = padding.left + index * step;
      const y = padding.top + innerHeight - ratio * innerHeight;
      return `
        <g data-series-index="${index}">
          <circle cx="${x}" cy="${y}" r="3.5" fill="var(--actual)"></circle>
          <rect x="${x - Math.max(10, step / 2)}" y="${padding.top}" width="${Math.max(20, step)}" height="${innerHeight}" fill="transparent"></rect>
        </g>
      `;
    })
    .join("");

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
    <path d="${path}" fill="none" stroke="var(--actual)" stroke-width="3.2" stroke-linejoin="round"></path>
    <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(83,102,119,0.24)" />
    <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(83,102,119,0.24)" />
    ${markers}
    ${xLabels}
  `;
  attachTooltipHandlers(svg, numericSeries);
}

function renderVisualization(payload) {
  renderChart(payload.series || []);
  setHtml(
    "visualStats",
    [
      { label: "当前指标", value: payload.indicator_label || payload.indicator },
      { label: "平均值", value: formatNumber(payload.stats?.mean, 2) },
      { label: "最新值", value: formatNumber(payload.stats?.latest, 2) },
      { label: "相邻变化", value: formatNumber(payload.stats?.delta, 2) },
    ]
      .map((item) => `<article class="stat-card"><span>${item.label}</span><strong>${item.value}</strong></article>`)
      .join("")
  );
  renderTable(
    "visualCorrelationTable",
    payload.correlations || [],
    [
      { key: "feature_label", label: "相关指标" },
      { key: "correlation", label: "相关系数" },
      { key: "sample_size", label: "样本数" },
    ],
    "暂无相关性结果。"
  );
}

function renderCrossModalGallery(assets) {
  const container = document.getElementById("crossModalGallery");
  if (!container) {
    return;
  }
  const visibleAssets = (assets || []).filter((asset) => asset.preview_url).slice(0, 8);
  if (!visibleAssets.length) {
    container.innerHTML = `<p class="muted">暂无 UAV 预览图。</p>`;
    return;
  }
  container.innerHTML = visibleAssets
    .map((asset) => {
      const mediaLabel =
        asset.media_type === "video"
          ? `视频：${formatNumber(asset.duration_seconds, 1)} 秒`
          : "图片";
      return `
        <article class="media-card">
          <img src="${escapeHtml(asset.preview_url)}" alt="${escapeHtml(asset.file_name || "UAV asset")}">
          <div class="media-card-body">
            <div class="media-card-title">${escapeHtml(formatMaybeDate(asset.sample_date))}</div>
            <div class="media-card-meta">Transformer分量1：${escapeHtml(formatNumber(asset.visual_transformer_embedding_01, 3))}</div>
            <div class="media-card-meta">${escapeHtml(mediaLabel)} · ${escapeHtml(asset.file_name || "")}</div>
            <div class="media-card-meta">视觉浊度代理：${escapeHtml(formatNumber(asset.turbidity_visual_proxy, 3))}</div>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderCrossModalEvaluation(evaluation) {
  const statsContainer = document.getElementById("crossModalEvaluationStats");
  const tableContainer = document.getElementById("crossModalEvaluationTable");
  if (!statsContainer || !tableContainer) {
    return;
  }
  if (!evaluation || !Array.isArray(evaluation.metric_rows) || !evaluation.metric_rows.length) {
    statsContainer.innerHTML = `<article class="stat-card"><span>模型前后对比</span><strong>暂无评估产物</strong></article>`;
    tableContainer.innerHTML = "";
    return;
  }
  const targets = evaluation.targets || {};
  const turbidity = targets.turbidity_ntu || {};
  const secchi = targets.secchi_depth_m || {};
  setHtml(
    "crossModalEvaluationStats",
    [
      { label: "评估样本", value: `${formatNumber(evaluation.sample_count, 0)} 行` },
      { label: "验证方式", value: evaluation.cv_strategy || "leave_one_out" },
      { label: "浊度最佳", value: turbidity.best_display_name || "-" },
      { label: "浊度RMSE", value: formatNumber(turbidity.best_rmse, 2) },
      { label: "透明度最佳", value: secchi.best_display_name || "-" },
      { label: "透明度RMSE", value: formatNumber(secchi.best_rmse, 3) },
    ]
      .map((item) => `<article class="stat-card"><span>${item.label}</span><strong>${escapeHtml(item.value)}</strong></article>`)
      .join("")
  );
  const metricRows = evaluation.metric_rows.map((row) => ({
    ...row,
    rmse: formatNumber(row.rmse, row.target === "secchi_depth_m" ? 3 : 2),
    mae: formatNumber(row.mae, row.target === "secchi_depth_m" ? 3 : 2),
    r2: formatNumber(row.r2, 3),
    success_rate: `${formatNumber(Number(row.success_rate) * 100, 1)}%`,
    rmse_reduction_pct_vs_baseline: `${formatNumber(row.rmse_reduction_pct_vs_baseline, 1)}%`,
  }));
  renderTable(
    "crossModalEvaluationTable",
    metricRows,
    [
      { key: "target_label", label: "目标" },
      { key: "display_name", label: "模型方案" },
      { key: "feature_count", label: "特征数" },
      { key: "sample_count", label: "样本数" },
      { key: "rmse", label: "RMSE" },
      { key: "mae", label: "MAE" },
      { key: "r2", label: "R2" },
      { key: "success_rate", label: "成功率" },
      { key: "rmse_reduction_pct_vs_baseline", label: "RMSE较前变化" },
    ],
    "暂无模型前后对比结果。"
  );
}

function renderCrossModal(payload) {
  const counts = payload.counts || {};
  const ranges = payload.date_ranges || {};
  setHtml(
    "crossModalStats",
    [
      { label: "UAV素材", value: `${formatNumber(counts.uav_assets, 0)} 个` },
      { label: "实地监测", value: `${formatNumber(counts.field_monitoring_zhangjiabang_rows, 0)} 组` },
      { label: "融合样本", value: `${formatNumber(counts.cross_modal_rows, 0)} 行` },
      { label: "同日强监督", value: `${formatNumber(counts.strong_same_day_cross_modal_rows, 0)} 行` },
      { label: "监督/弱监督", value: `${formatNumber(counts.supervised_cross_modal_rows, 0)} 行` },
      { label: "UAV日期", value: `${formatMaybeDate(ranges.uav?.start)} - ${formatMaybeDate(ranges.uav?.end)}` },
    ]
      .map((item) => `<article class="stat-card"><span>${item.label}</span><strong>${item.value}</strong></article>`)
      .join("")
  );
  renderCrossModalEvaluation(payload.model_evaluation);
  renderCrossModalGallery(payload.preview_assets || []);
  renderTable(
    "crossModalTable",
    payload.daily_rows || [],
    [
      { key: "sample_date", label: "UAV日期" },
      { key: "field_sample_date", label: "实测日期" },
      { key: "label_alignment", label: "标签对齐" },
      { key: "turbidity_ntu", label: "实测浊度" },
      { key: "secchi_depth_m", label: "透明度" },
      { key: "uav_asset_count", label: "UAV素材" },
      { key: "uav_turbidity_visual_proxy_mean", label: "视觉浊度代理" },
      { key: "uav_visual_transformer_embedding_01_mean", label: "Transformer分量1" },
      { key: "uav_sharpness_laplacian_mean", label: "清晰度" },
      { key: "fusion_readiness", label: "融合状态" },
    ],
    "暂无张家浜跨模态融合结果。"
  );
}

async function loadVisualization() {
  const stationCode = document.getElementById("visualStationCode")?.value || "2586";
  const indicator = document.getElementById("visualIndicator")?.value || "turbidity";
  setLoadingState("visualStats", 4);
  setLoadingState("visualCorrelationTable", 6);
  const payload = await fetchJson(
    `/api/v1/visualization/summary?station_code=${stationCode}&indicator=${indicator}&limit=180`
  );
  renderVisualization(payload);
  setText("sidebarContext", payload.station?.station_name || stationCode);
}

async function loadCrossModal() {
  setLoadingState("crossModalStats", 6);
  setLoadingState("crossModalEvaluationStats", 6);
  setLoadingState("crossModalEvaluationTable", 6);
  setLoadingState("crossModalTable", 6);
  const payload = await fetchJson("/api/v1/cross-modal/zhangjiabang");
  renderCrossModal(payload);
}

if (initAuthenticatedShell()) {
  fetchJsonSafe("database-stations", "/api/v1/database/stations").then((stationsResult) => {
    if (stationsResult.ok) {
      populateStations(stationsResult.data);
    }
  });
  fetchJsonSafe("database-summary", "/api/v1/database/summary").then((summaryResult) => {
    if (summaryResult.ok) {
      populateIndicators(summaryResult.data.key_indicators || []);
      loadVisualization().catch((error) => {
        showStatus(`加载失败：${error.message}`, "error");
      });
      loadCrossModal().catch((error) => {
        showStatus(`跨模态数据加载失败：${error.message}`, "error");
      });
    }
  });
  document.getElementById("visualFilterForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadVisualization().catch((error) => {
      showStatus(`刷新失败：${error.message}`, "error");
    });
  });
}
