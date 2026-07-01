import { fetchJsonSafe } from "./api.js";
import { renderTable, setLoadingState } from "./base.js";
import { initAuthenticatedShell } from "./app-shell.js";

function showStatus(message, type = "warning") {
  const banner = document.getElementById("uploadStatus");
  if (!banner) {
    return;
  }
  banner.textContent = message;
  banner.className = message ? `status-banner ${type}` : "status-banner hidden";
}

function updateUploadProgress(percent, message) {
  const bar = document.getElementById("uploadProgressBar");
  const text = document.getElementById("uploadProgressText");
  if (bar) {
    bar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  }
  if (text) {
    text.textContent = message;
  }
}

function setUploadPending(pending) {
  const submitButton = document.getElementById("uploadSubmitButton");
  if (!submitButton) {
    return;
  }
  submitButton.disabled = pending;
  submitButton.classList.toggle("is-loading", pending);
  submitButton.textContent = pending ? "正在上传..." : "保存数据文件";
}

function populateStations(stations) {
  const select = document.getElementById("uploadStationCode");
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

async function loadImports() {
  setLoadingState("uploadTable", 6);
  const [stationsResult, importsResult] = await Promise.all([
    fetchJsonSafe("database-stations", "/api/v1/database/stations"),
    fetchJsonSafe("imports", "/api/v1/data/imports"),
  ]);
  if (stationsResult.ok) {
    populateStations(stationsResult.data);
  }
  if (importsResult.ok) {
    renderTable(
      "uploadTable",
      importsResult.data || [],
      [
        { key: "source_name", label: "文件名称" },
        { key: "data_type", label: "数据类型" },
        { key: "created_at", label: "上传时间" },
        { key: "status", label: "上传状态" },
        { key: "rows_detected", label: "行数" },
        { key: "stored_path", label: "存储路径" },
      ],
      "暂无上传记录。"
    );
  }
}

function uploadWithProgress(formData) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/data/upload", true);
    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) {
        updateUploadProgress(50, "正在上传，请稍候...");
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      updateUploadProgress(percent, `正在上传：${percent}%`);
    });
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
        return;
      }
      try {
        const payload = JSON.parse(xhr.responseText);
        reject(new Error(payload.detail || xhr.statusText));
      } catch {
        reject(new Error(xhr.statusText || "Upload failed."));
      }
    };
    xhr.onerror = () => reject(new Error("Network error."));
    xhr.send(formData);
  });
}

async function handleUpload(event) {
  event.preventDefault();
  const fileInput = document.getElementById("uploadFiles");
  const files = Array.from(fileInput?.files || []);
  if (!files.length) {
    showStatus("请先选择要上传的文件。", "warning");
    return;
  }
  const formData = new FormData();
  formData.set("data_type", document.getElementById("uploadDataType")?.value || "water_quality");
  formData.set("station_code", document.getElementById("uploadStationCode")?.value || "2586");
  formData.set("time_granularity", "daily");
  files.forEach((file) => formData.append("files", file));

  setUploadPending(true);
  showStatus("正在上传，请稍候...", "warning");
  updateUploadProgress(0, "正在准备上传...");
  try {
    const result = await uploadWithProgress(formData);
    updateUploadProgress(100, `上传完成，共处理 ${result.uploaded_count} 个文件。`);
    showStatus(`已完成 ${result.uploaded_count} 个文件上传。`, "success");
    if (fileInput) {
      fileInput.value = "";
    }
    await loadImports();
  } finally {
    setUploadPending(false);
  }
}

if (initAuthenticatedShell()) {
  document.getElementById("uploadForm")?.addEventListener("submit", (event) => {
    handleUpload(event).catch((error) => {
      showStatus(`上传失败：${error.message}`, "error");
      updateUploadProgress(0, "上传失败，请检查网络或文件格式后重试。");
    });
  });
  document.getElementById("uploadResetButton")?.addEventListener("click", () => {
    const fileInput = document.getElementById("uploadFiles");
    if (fileInput) {
      fileInput.value = "";
    }
    updateUploadProgress(0, "已清空已选文件。");
    showStatus("", "hidden");
  });
  document.getElementById("uploadRefreshButton")?.addEventListener("click", () => {
    loadImports().catch((error) => {
      showStatus(`刷新失败：${error.message}`, "error");
    });
  });
  loadImports().catch((error) => {
    showStatus(`加载失败：${error.message}`, "error");
  });
}
