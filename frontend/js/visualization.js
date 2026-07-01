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
        `<option value="${station.station_code}" ${station.station_code === "2586" ? "selected" : ""}>${station.station_code} - ${station.station_name}</option>`
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
        `<option value="${item.key}" ${item.key === "turbidity" ? "selected" : ""}>${item.label}</option>`
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
    }
  });
  document.getElementById("visualFilterForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadVisualization().catch((error) => {
      showStatus(`刷新失败：${error.message}`, "error");
    });
  });
}
