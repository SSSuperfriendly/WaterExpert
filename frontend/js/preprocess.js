import { fetchJson, fetchJsonSafe } from "./api.js";
import { formatNumber, renderTable, setHtml, setText } from "./base.js";
import { initAuthenticatedShell } from "./app-shell.js";

function showStatus(message, type = "warning") {
  const banner = document.getElementById("preprocessStatus");
  if (!banner) {
    return;
  }
  banner.textContent = message;
  banner.className = `status-banner ${type}`;
}

function populateStations(stations) {
  const select = document.getElementById("preprocessStationCode");
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

function renderSummary(payload) {
  setHtml(
    "preprocessStats",
    [
      { label: "分析样本", value: formatNumber(payload.rows_analyzed, 0) },
      { label: "起始日期", value: payload.date_start || "N/A" },
      { label: "结束日期", value: payload.date_end || "N/A" },
      { label: "缺失单元", value: formatNumber(payload.total_missing_cells, 0) },
      { label: "异常标记", value: formatNumber(payload.total_outlier_flags, 0) },
    ]
      .map((item) => `<article class="stat-card"><span>${item.label}</span><strong>${item.value}</strong></article>`)
      .join("")
  );
  setHtml(
    "preprocessRecommendations",
    (payload.recommendations || []).map((item) => `<li>${item}</li>`).join("")
  );
  renderTable(
    "preprocessTable",
    payload.feature_profiles || [],
    [
      { key: "feature_label", label: "指标" },
      { key: "valid_count", label: "有效值" },
      { key: "missing_count", label: "缺失值" },
      { key: "missing_rate", label: "缺失率" },
      { key: "mean", label: "均值" },
      { key: "std", label: "标准差" },
      { key: "outlier_count", label: "异常值" },
      { key: "standardization_hint", label: "处理建议" },
    ],
    "暂无预处理摘要。"
  );
}

async function loadSummary() {
  const stationCode = document.getElementById("preprocessStationCode")?.value || "2586";
  const payload = await fetchJson(`/api/v1/preprocess/summary?station_code=${stationCode}`);
  renderSummary(payload);
  setText("sidebarContext", payload.station?.station_name || stationCode);
}

if (initAuthenticatedShell()) {
  fetchJsonSafe("database-stations", "/api/v1/database/stations").then((result) => {
    if (result.ok) {
      populateStations(result.data);
      loadSummary().catch((error) => {
        showStatus(`加载失败：${error.message}`, "error");
      });
    }
  });
  document.getElementById("preprocessFilterForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadSummary().catch((error) => {
      showStatus(`刷新失败：${error.message}`, "error");
    });
  });
}
