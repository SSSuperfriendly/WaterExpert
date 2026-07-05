import { bindAsyncEvent, flash, getElement, state, summarizeIssues } from "./base.js";
import { buildApiUrl, fetchJsonSafe } from "./api.js";
import { initAuthenticatedShell } from "./app-shell.js";
import { renderPredictionChart, renderPredictionControls } from "./chart.js";
import { renderOverview } from "./dashboard.js";
import { openReportExportDialog } from "./export.js";
import {
  initAnalysisPage,
  loadThresholds,
  renderBoundary,
  renderDiagnostics,
  renderPlaybookAndSobol,
  renderRealtimeValidation,
  renderTriage,
} from "./analysis.js";
import {
  createJobPoller,
  handleImportSubmit,
  handleJobSubmit,
  loadStaticData,
  refreshOperationalData,
} from "./jobs.js";

let jobPoller = null;
const profile = initAuthenticatedShell();

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

async function loadArtifactData(jobId = state.activeJobId, { silent = false } = {}) {
  const params = jobId ? { job_id: jobId } : {};
  const [metaResult, dashboardResult, diagnosticsResult, triageResult, boundaryResult, playbookResult, sensitivityResult, realtimeValidationResult] = await Promise.all([
    fetchJsonSafe("meta", buildApiUrl("/api/v1/meta", params)),
    fetchJsonSafe("dashboard", buildApiUrl("/api/v1/dashboard", params)),
    fetchJsonSafe("diagnostics", buildApiUrl("/api/v1/diagnostics", params)),
    fetchJsonSafe("scenario-triage", buildApiUrl("/api/v1/scenario-triage", params)),
    fetchJsonSafe("boundary", buildApiUrl("/api/v1/boundary", params)),
    fetchJsonSafe("response-playbook", buildApiUrl("/api/v1/response-playbook", params)),
    fetchJsonSafe("sensitivity", buildApiUrl("/api/v1/sensitivity", params)),
    fetchJsonSafe("realtime-validation", "/api/v1/realtime-validation"),
  ]);

  state.meta = metaResult.ok ? metaResult.data : null;
  state.dashboard = dashboardResult.ok ? dashboardResult.data : null;
  state.diagnostics = diagnosticsResult.ok ? diagnosticsResult.data : null;
  state.triage = triageResult.ok ? triageResult.data : null;
  state.boundary = boundaryResult.ok ? boundaryResult.data : null;
  state.playbook = playbookResult.ok ? playbookResult.data : null;
  state.sensitivity = sensitivityResult.ok ? sensitivityResult.data : null;
  state.realtimeValidation = realtimeValidationResult.ok ? realtimeValidationResult.data : null;

  const predictionResult = await loadPredictions(null, jobId);
  const thresholdResult = await loadThresholds(jobId, state.currentThresholdFeature);

  renderOverview();
  renderDiagnostics();
  renderTriage();
  renderBoundary();
  renderPlaybookAndSobol();
  renderRealtimeValidation();

  const issues = [
    metaResult,
    dashboardResult,
    diagnosticsResult,
    triageResult,
    boundaryResult,
    playbookResult,
    sensitivityResult,
    realtimeValidationResult,
    predictionResult,
    thresholdResult,
  ].filter((item) => !item.ok);
  if (!silent) {
    summarizeIssues(issues, "");
  }
  return issues;
}

async function loadAll({ silent = false } = {}) {
  const staticIssues = await loadStaticData();
  const operationalIssues = await refreshOperationalData(jobPoller, { silent: true });
  const artifactIssues = await loadArtifactData(state.activeJobId, { silent: true });
  const issues = [...staticIssues, ...operationalIssues, ...artifactIssues];
  if (!silent) {
    summarizeIssues(issues, "");
  }
}

if (profile) {
  jobPoller = createJobPoller({
    refreshOperationalData: (options) => refreshOperationalData(jobPoller, options),
    loadArtifactData,
  });

  bindAsyncEvent(
    getElement("refreshButton"),
    "click",
    async () => {
      await loadAll();
    },
    "刷新失败"
  );

  const exportReportButton = getElement("exportReportButton");
  if (exportReportButton) {
    exportReportButton.addEventListener("click", () => {
      openReportExportDialog();
    });
  }

  bindAsyncEvent(
    getElement("importForm"),
    "submit",
    (event) => handleImportSubmit(event, () => refreshOperationalData(jobPoller, { silent: true })),
    "导入失败"
  );
  bindAsyncEvent(
    getElement("jobForm"),
    "submit",
    (event) =>
      handleJobSubmit(event, {
        refreshOperationalData: () => refreshOperationalData(jobPoller, { silent: true }),
        loadArtifactData,
      }),
    "任务创建失败"
  );
  bindAsyncEvent(
    getElement("modelSelect"),
    "change",
    async (event) => {
      const result = await loadPredictions(event.target.value, state.activeJobId);
      summarizeIssues(result.ok ? [] : [result], "模型切换成功。");
    },
    "模型切换失败"
  );
  bindAsyncEvent(
    getElement("thresholdSelect"),
    "change",
    async (event) => {
      const result = await loadThresholds(state.activeJobId, event.target.value);
      summarizeIssues(result.ok ? [] : [result], "阈值加载成功。");
    },
    "阈值加载失败"
  );
  bindAsyncEvent(
    getElement("jobViewSelect"),
    "change",
    async (event) => {
      state.activeJobId = event.target.value;
      await loadArtifactData(state.activeJobId, { silent: false });
    },
    "任务产物切换失败"
  );

  initAnalysisPage();

  loadAll().catch((error) => {
    console.error(error);
    flash(`加载失败: ${error.message}`, "error");
  });
}
