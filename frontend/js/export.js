import {
  REPORT_EXPORT_FORMATS,
  clearFlash,
  flash,
  getElement,
  showDownloadAlert,
  state,
} from "./base.js";
import { buildApiUrl, fetchBlob, fetchJson } from "./api.js";

const REPORT_PREVIEW = {
  html: "适合浏览器查看，包含概览、预测、阈值、分诊与敏感性摘要。",
  md: "适合版本管理与文本审阅，便于继续编辑报告内容。",
  json: "适合程序消费，保留结构化字段与下游系统接入。",
  pdf: "适合正式汇报和打印，版式稳定。",
};

export function getReportFormatMeta(format) {
  return REPORT_EXPORT_FORMATS[format] || REPORT_EXPORT_FORMATS.html;
}

export function ensureReportFilename(filename, format) {
  const meta = getReportFormatMeta(format);
  const safeName = String(filename || `waterexpert-software-report${meta.extension}`);
  return safeName.endsWith(meta.extension) ? safeName : `${safeName}${meta.extension}`;
}

export function closeDialogElement(dialog) {
  if (!dialog) {
    return;
  }
  if (typeof dialog.close === "function") {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
  }
}

export function downloadBlob(blob, filename) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => {
    window.URL.revokeObjectURL(objectUrl);
  }, 1000);
}

export async function saveBlobToUserLocation(blob, filename, format) {
  const normalizedFilename = ensureReportFilename(filename, format);
  const meta = getReportFormatMeta(format);
  if (typeof window.showSaveFilePicker !== "function") {
    downloadBlob(blob, normalizedFilename);
    return { mode: "download", filename: normalizedFilename };
  }

  const handle = await window.showSaveFilePicker({
    suggestedName: normalizedFilename,
    types: [
      {
        description: `${meta.label} 报告`,
        accept: {
          [meta.mime]: [meta.extension],
        },
      },
    ],
  });
  const writable = await handle.createWritable();
  await writable.write(blob);
  await writable.close();
  return { mode: "picker", filename: handle.name || normalizedFilename };
}

export function buildDownloadSuccessMessage(result) {
  return result.mode === "picker"
    ? `导出成功\n${result.filename}`
    : `浏览器已开始下载\n${result.filename}`;
}

export async function exportReport(format = "html") {
  try {
    const url = buildApiUrl("/api/v1/report/export", {
      ...(state.activeJobId ? { job_id: state.activeJobId } : {}),
      format,
    });
    const payload = await fetchJson(url, { method: "POST" });
    const blob = await fetchBlob(payload.download_url);
    const result = await saveBlobToUserLocation(blob, payload.filename, format);
    flash(`报告已导出：${result.filename}`);
    showDownloadAlert(buildDownloadSuccessMessage(result));
    return true;
  } catch (error) {
    if (error?.name === "AbortError") {
      clearFlash();
      return false;
    }
    showDownloadAlert(`导出失败\n${error.message}`);
    throw error;
  }
}

export function ensureReportExportDialog() {
  let dialog = getElement("reportExportDialog");
  if (dialog) {
    return dialog;
  }

  dialog = document.createElement("dialog");
  dialog.id = "reportExportDialog";
  dialog.className = "export-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="export-dialog-card" id="reportExportForm">
      <div class="export-dialog-head">
        <h2>导出报告</h2>
      </div>
      <label class="field">
        <span>格式</span>
        <select id="reportExportFormat">
          <option value="html">HTML</option>
          <option value="md">Markdown</option>
          <option value="json">JSON</option>
          <option value="pdf">PDF</option>
        </select>
      </label>
      <p id="reportExportPreview" class="muted">${REPORT_PREVIEW.html}</p>
      <ul class="simple-list">
        <li>报告包含系统概览、预测快照、阈值检索、场景分诊与敏感性摘要。</li>
        <li>PDF 与 HTML 更适合汇报，JSON 更适合集成，Markdown 更适合继续编辑。</li>
      </ul>
      <div class="export-dialog-actions">
        <button id="reportExportCancel" type="button" class="button button-secondary">取消</button>
        <button id="reportExportConfirm" type="submit" class="button button-primary">选择位置并导出</button>
      </div>
    </form>
  `;
  document.body.appendChild(dialog);

  const preview = () => {
    const format = getElement("reportExportFormat")?.value || "html";
    const previewBox = getElement("reportExportPreview");
    if (previewBox) {
      previewBox.textContent = REPORT_PREVIEW[format];
    }
  };

  const closeDialog = () => closeDialogElement(dialog);

  getElement("reportExportCancel")?.addEventListener("click", closeDialog);
  getElement("reportExportFormat")?.addEventListener("change", preview);

  getElement("reportExportForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const confirmButton = getElement("reportExportConfirm");
    const selectedFormat = getElement("reportExportFormat")?.value || "html";
    if (confirmButton) {
      confirmButton.setAttribute("disabled", "disabled");
    }
    try {
      const saved = await exportReport(selectedFormat);
      if (saved) {
        closeDialog();
      }
    } catch (error) {
      flash(`导出失败: ${error.message}`, "error");
    } finally {
      if (confirmButton) {
        confirmButton.removeAttribute("disabled");
      }
    }
  });

  return dialog;
}

export function openReportExportDialog() {
  const dialog = ensureReportExportDialog();
  if (dialog.open) {
    return;
  }
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "open");
  }
}
