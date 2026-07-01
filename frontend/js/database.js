import { fetchJson, fetchJsonSafe } from "./api.js";
import { formatNumber, renderTable, setHtml, setLoadingState, setText, state } from "./base.js";
import { initAuthenticatedShell } from "./app-shell.js";

const PAGE_SIZE = 120;

function showStatus(message, type = "warning") {
  const banner = document.getElementById("databaseStatus");
  if (!banner) {
    return;
  }
  banner.textContent = message;
  banner.className = message ? `status-banner ${type}` : "status-banner hidden";
}

function renderSummary(summary) {
  setHtml(
    "databaseStats",
    [
      { label: "累计监测记录", value: formatNumber(summary.total_records, 0) },
      { label: "覆盖站点", value: formatNumber(summary.total_stations, 0) },
      { label: "起始日期", value: summary.date_start || "N/A" },
      { label: "结束日期", value: summary.date_end || "N/A" },
    ]
      .map((item) => `<article class="stat-card"><span>${item.label}</span><strong>${item.value}</strong></article>`)
      .join("")
  );
}

function populateStations(stations) {
  const select = document.getElementById("databaseStationCode");
  if (!select) {
    return;
  }
  select.innerHTML = [
    `<option value="">全部站点</option>`,
    ...stations.map(
      (station) =>
        `<option value="${station.station_code}">${station.station_code} - ${station.station_name}</option>`
    ),
  ].join("");
}

function currentFilters() {
  return {
    station_code: document.getElementById("databaseStationCode")?.value || "",
    keyword: document.getElementById("databaseKeyword")?.value || "",
    start_date: document.getElementById("databaseStartDate")?.value || "",
    end_date: document.getElementById("databaseEndDate")?.value || "",
  };
}

function renderPager(payload) {
  const pager = document.getElementById("databasePager");
  if (!pager) {
    return;
  }
  const pagination = payload.pagination || {};
  if (!payload.matched_rows) {
    pager.innerHTML = "";
    return;
  }
  pager.innerHTML = `
    <div class="pager-summary">
      当前显示 ${pagination.showing_from}-${pagination.showing_to} / 共 ${formatNumber(payload.matched_rows, 0)} 条
    </div>
    <div class="pager-actions">
      <button id="databasePrevPage" class="button button-secondary" ${pagination.has_previous ? "" : "disabled"}>上一页</button>
      <span class="pager-page">第 ${pagination.page} / ${pagination.total_pages} 页</span>
      <button id="databaseNextPage" class="button button-secondary" ${pagination.has_next ? "" : "disabled"}>下一页</button>
    </div>
  `;
  document.getElementById("databasePrevPage")?.addEventListener("click", () => {
    runQuery(Math.max(0, pagination.offset - PAGE_SIZE)).catch((error) => {
      showStatus(`翻页失败：${error.message}`, "error");
    });
  });
  document.getElementById("databaseNextPage")?.addEventListener("click", () => {
    runQuery(pagination.offset + PAGE_SIZE).catch((error) => {
      showStatus(`翻页失败：${error.message}`, "error");
    });
  });
}

function renderQuery(payload) {
  state.databaseQuery = payload;
  const summary = payload.summary || {};
  setHtml(
    "databaseQuerySummary",
    [
      `命中记录 ${formatNumber(payload.matched_rows, 0)} 条`,
      `当前返回 ${formatNumber(payload.returned_rows, 0)} 条`,
      `覆盖站点 ${formatNumber(summary.station_count, 0)} 个`,
      `平均浊度 ${formatNumber(summary.mean_turbidity, 2)}`,
      `平均透明度 ${formatNumber(summary.mean_secchi_depth, 2)}`,
    ].map((item) => `<span>${item}</span>`).join("")
  );
  renderTable(
    "databaseTable",
    payload.rows || [],
    [
      { key: "date", label: "日期" },
      { key: "station_code", label: "站点编号" },
      { key: "station_name", label: "站点" },
      { key: "river", label: "河流" },
      { key: "turbidity", label: "浊度" },
      { key: "secchi_depth_sd_m", label: "透明度" },
      { key: "ph", label: "pH" },
      { key: "dissolved_oxygen", label: "溶解氧" },
      { key: "tn", label: "总氮" },
      { key: "tp", label: "总磷" },
    ],
    "当前筛选条件下暂无数据。"
  );
  renderPager(payload);
}

async function runQuery(offset = 0) {
  setLoadingState("databaseTable", 8);
  const params = new URLSearchParams(currentFilters());
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(offset));
  const payload = await fetchJson(`/api/v1/database/query?${params.toString()}`);
  renderQuery(payload);
  setText("sidebarContext", currentFilters().station_code || "全站数据库");
}

async function loadPage() {
  setLoadingState("databaseStats", 4);
  setLoadingState("databaseTable", 8);
  const [summaryResult, stationsResult] = await Promise.all([
    fetchJsonSafe("database-summary", "/api/v1/database/summary"),
    fetchJsonSafe("database-stations", "/api/v1/database/stations"),
  ]);
  if (summaryResult.ok) {
    renderSummary(summaryResult.data);
  }
  if (stationsResult.ok) {
    populateStations(stationsResult.data);
  }
  await runQuery(0);
}

if (initAuthenticatedShell()) {
  document.getElementById("databaseFilterForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    runQuery(0).catch((error) => {
      showStatus(`查询失败：${error.message}`, "error");
    });
  });
  document.getElementById("databaseRefreshButton")?.addEventListener("click", () => {
    loadPage().catch((error) => {
      showStatus(`刷新失败：${error.message}`, "error");
    });
  });
  loadPage().catch((error) => {
    showStatus(`加载失败：${error.message}`, "error");
  });
}
