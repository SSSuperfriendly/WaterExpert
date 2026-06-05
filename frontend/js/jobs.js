import {
  JOB_POLL_INTERVAL_MS,
  flash,
  getChecked,
  getValue,
  populateStationInputs,
  renderImports,
  renderJobs,
  state,
  summarizeIssues,
} from "./base.js";
import { buildApiUrl, fetchJson, fetchJsonSafe } from "./api.js";

export async function handleImportSubmit(event, refreshOperationalData) {
  event.preventDefault();
  const payload = {
    data_type: getValue("importDataType"),
    source_name: getValue("importSourceName"),
    file_path: getValue("importFilePath"),
    time_granularity: getValue("importGranularity"),
    station_code: getValue("importStationCode"),
  };
  const result = await fetchJson("/api/v1/data/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  flash(`数据导入记录已创建: ${result.status}`);
  document.getElementById("importForm")?.reset();
  const importGranularity = document.getElementById("importGranularity");
  if (importGranularity) {
    importGranularity.value = "daily";
  }
  populateStationInputs();
  await refreshOperationalData();
}

export async function handleJobSubmit(event, actions) {
  const { refreshOperationalData, loadArtifactData } = actions;
  event.preventDefault();
  const payload = {
    mode: getValue("jobMode"),
    model_name: getValue("jobModelName"),
    station_code: getValue("jobStationCode"),
    start_date: getValue("jobStartDate") || null,
    end_date: getValue("jobEndDate") || null,
    use_existing_artifacts: getChecked("jobUseExisting"),
  };
  const result = await fetchJson("/api/v1/prediction-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshOperationalData();
  if (payload.use_existing_artifacts) {
    state.activeJobId = result.job_id;
    await loadArtifactData(state.activeJobId, { silent: true });
    flash(`预测任务已创建并已切换到任务产物视图: ${result.job_id}`);
  } else {
    state.pendingJobSelectionId = result.job_id;
    flash(`预测任务已创建: ${result.job_id} (${result.status})，系统将自动轮询直到完成。`);
  }
}

export function createJobPoller({ refreshOperationalData, loadArtifactData }) {
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

    schedule();
  }

  function stop() {
    if (state.pollTimer) {
      window.clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function schedule() {
    stop();
    if ((state.jobs || []).some((job) => job.status === "running")) {
      state.pollTimer = window.setTimeout(() => {
        pollJobs().catch((error) => {
          flash(`任务轮询失败: ${error.message}`, "error");
        });
      }, JOB_POLL_INTERVAL_MS);
    }
  }

  return { pollJobs, stop, schedule };
}

export async function loadStaticData() {
  const [stationsResult] = await Promise.all([
    fetchJsonSafe("stations", "/api/v1/stations"),
  ]);
  state.stations = stationsResult.ok ? stationsResult.data : [];
  populateStationInputs();
  return [stationsResult].filter((item) => !item.ok);
}

export async function refreshOperationalData(jobPoller, { silent = false } = {}) {
  const [importsResult, jobsResult] = await Promise.all([
    fetchJsonSafe("imports", "/api/v1/data/imports"),
    fetchJsonSafe("jobs", "/api/v1/prediction-jobs"),
  ]);
  state.imports = importsResult.ok ? importsResult.data : [];
  state.jobs = jobsResult.ok ? jobsResult.data : [];
  renderImports();
  renderJobs();
  jobPoller?.schedule();
  const issues = [importsResult, jobsResult].filter((item) => !item.ok);
  if (!silent && issues.length) {
    summarizeIssues(issues, "");
  }
  return issues;
}


