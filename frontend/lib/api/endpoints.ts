"use client";

import { apiClient, apiBaseUrl } from "./client";
import type {
  BoundarySummary,
  Case,
  CaseSummary,
  CredentialHint,
  DashboardPayload,
  DatabaseSummary,
  Dataset,
  DatasetFreshness,
  DatasetPreview,
  DatasetQualityReport,
  DatasetVersion,
  DiagnosticsPayload,
  JobArtifact,
  JobQueueSnapshot,
  KgBuildJob,
  KgFileInfo,
  KgGraphPayload,
  KgQaResult,
  KnowledgeGraphSummary,
  LoginResponse,
  PredictionsPayload,
  PredictionJob,
  PreprocessSummary,
  Provenance,
  QueryResult,
  RealtimeValidation,
  ReportExportResult,
  ScenarioTriagePayload,
  SensitivityPayload,
  ThresholdsPayload,
  VisualizationPayload,
  ReportFormat,
  PlaybookPayload,
  ModelVersion,
  ModelSummary,
  ReportRecord,
  ReportSummary,
  EventRecord,
  EventSummary,
} from "./contracts";

/** Selectors shared by every result endpoint (review item 5). */
export interface ArtifactScope {
  case_id?: string;
  job_id?: string;
  scope?: string;
  [key: string]: string | number | boolean | undefined | null;
}

export const endpoints = {
  // Auth
  login: (username: string, password: string) =>
    apiClient.post<LoginResponse>("/api/v1/auth/login", { username, password }),
  credentialHint: () => apiClient.get<CredentialHint>("/api/v1/auth/hint"),
  register: (payload: {
    username: string;
    email: string;
    password: string;
    confirm_password: string;
  }) => apiClient.post<LoginResponse>("/api/v1/auth/register", payload),
  forgotPassword: (email: string) =>
    apiClient.post<null>("/api/v1/auth/forgot-password", { email }),
  resetPassword: (token: string, password: string) =>
    apiClient.post<null>("/api/v1/auth/reset-password", { token, password }),
  githubOAuthAuthorize: () =>
    apiClient.get<{ authorization_url: string }>(
      "/api/v1/auth/oauth/github/authorize"
    ),
  githubOAuthUrl: () => `${apiBaseUrl()}/api/v1/auth/oauth/github/authorize`,

  // Meta & overview
  meta: () => apiClient.get<Record<string, unknown>>("/api/v1/meta"),
  dashboard: (scope: ArtifactScope = {}) =>
    apiClient.get<DashboardPayload & { provenance?: Provenance }>("/api/v1/dashboard", scope),
  stations: () => apiClient.get<Record<string, unknown>>("/api/v1/stations"),

  // Database
  databaseSummary: () => apiClient.get<DatabaseSummary>("/api/v1/database/summary"),
  databaseStations: () => apiClient.get<Record<string, unknown>>("/api/v1/database/stations"),
  query: (params: Record<string, string | number | undefined>) =>
    apiClient.get<QueryResult>("/api/v1/database/query", params),

  // Data asset centre. Every file goes through the same acceptance chain
  // (validate → map → clean → align → accept/reject) and carries a quality
  // grade; only accepted versions may feed a prediction run.
  datasets: (params?: { data_type?: string; status?: string }) =>
    apiClient.get<Dataset[]>("/api/v1/datasets", params),
  dataset: (datasetId: string) => apiClient.get<Dataset>(`/api/v1/datasets/${datasetId}`),
  uploadDataset: (formData: FormData) =>
    apiClient.upload<DatasetVersion>("/api/v1/datasets", formData),
  importDataset: (payload: {
    data_type: string;
    relative_path: string;
    station_code?: string;
    dataset_id?: string;
    title?: string;
  }) => apiClient.post<DatasetVersion>("/api/v1/datasets/import", payload),
  archiveDataset: (datasetId: string) =>
    apiClient.post<Dataset>(`/api/v1/datasets/${datasetId}/archive`, {}),
  deleteDataset: (datasetId: string) =>
    apiClient.delete<Record<string, unknown>>(`/api/v1/datasets/${datasetId}`),
  datasetVersions: (datasetId: string) =>
    apiClient.get<DatasetVersion[]>(`/api/v1/datasets/${datasetId}/versions`),
  datasetVersion: (versionId: string) =>
    apiClient.get<DatasetVersion>(`/api/v1/dataset-versions/${versionId}`),
  datasetQuality: (versionId: string) =>
    apiClient.get<DatasetQualityReport>(`/api/v1/dataset-versions/${versionId}/quality`),
  datasetPreview: (versionId: string, limit = 50) =>
    apiClient.get<DatasetPreview>(`/api/v1/dataset-versions/${versionId}/preview`, { limit }),
  datasetLineage: (versionId: string) =>
    apiClient.get<Record<string, unknown>>(`/api/v1/dataset-versions/${versionId}/lineage`),
  datasetFieldDictionary: (dataType: string) =>
    apiClient.get<Record<string, unknown>>(`/api/v1/datasets/field-dictionary/${dataType}`),
  datasetFreshness: () =>
    apiClient.get<DatasetFreshness>("/api/v1/datasets/freshness"),
  datasetQualityAlerts: (limit = 10) =>
    apiClient.get<DatasetVersion[]>("/api/v1/datasets/quality-alerts", { limit }),

  // Preprocess & visualization
  preprocessSummary: (stationCode = "2586") =>
    apiClient.get<PreprocessSummary>("/api/v1/preprocess/summary", {
      station_code: stationCode,
    }),
  visualization: (stationCode = "2586", indicator = "turbidity", limit = 180) =>
    apiClient.get<VisualizationPayload>("/api/v1/visualization/summary", {
      station_code: stationCode,
      indicator,
      limit,
    }),

  // Prediction jobs
  createJob: (payload: {
    model_name: string;
    station_code?: string;
    start_date?: string;
    end_date?: string;
    use_existing_artifacts?: boolean;
    case_id?: string;
    priority?: number;
  }) => apiClient.post<PredictionJob>("/api/v1/prediction-jobs", payload),
  jobs: () => apiClient.get<PredictionJob[]>("/api/v1/prediction-jobs"),
  jobQueue: () => apiClient.get<JobQueueSnapshot>("/api/v1/prediction-jobs/queue"),
  job: (jobId: string) => apiClient.get<PredictionJob>(`/api/v1/prediction-jobs/${jobId}`),
  jobSeries: (jobId: string) =>
    apiClient.get<unknown>(`/api/v1/prediction-jobs/${jobId}/series`),
  cancelJob: (jobId: string) =>
    apiClient.post<PredictionJob>(`/api/v1/prediction-jobs/${jobId}/cancel`),
  retryJob: (jobId: string) =>
    apiClient.post<PredictionJob>(`/api/v1/prediction-jobs/${jobId}/retry`),
  jobArtifacts: (jobId: string) =>
    apiClient.get<JobArtifact[]>(`/api/v1/prediction-jobs/${jobId}/artifacts`),
  jobLogUrl: (jobId: string, stream: "stdout" | "stderr") =>
    `/api/v1/prediction-jobs/${jobId}/logs/${stream}`,
  predictions: (params: { model?: string; split?: string } & ArtifactScope) =>
    apiClient.get<PredictionsPayload & { provenance?: Provenance }>("/api/v1/predictions", params),

  // Analysis cases — the object a result is attributed to.
  createCase: (payload: {
    title: string;
    description?: string;
    station_code?: string;
    target_date?: string;
    dataset_version_ids?: string[];
  }) => apiClient.post<Case>("/api/v1/cases", payload),
  cases: (params?: { owner?: string; status?: string; limit?: number }) =>
    apiClient.get<Case[]>("/api/v1/cases", params),
  caseSummary: () => apiClient.get<CaseSummary>("/api/v1/cases/summary"),
  case: (caseId: string) => apiClient.get<Case>(`/api/v1/cases/${caseId}`),
  updateCase: (caseId: string, payload: { title?: string; description?: string; target_date?: string }) =>
    apiClient.patch<Case>(`/api/v1/cases/${caseId}`, payload),
  archiveCase: (caseId: string) =>
    apiClient.post<Case>(`/api/v1/cases/${caseId}/archive`, {}),
  deleteCase: (caseId: string) =>
    apiClient.delete<Record<string, unknown>>(`/api/v1/cases/${caseId}`),
  caseProvenance: (caseId: string) =>
    apiClient.get<Provenance>(`/api/v1/cases/${caseId}/provenance`),
  runCase: (
    caseId: string,
    payload: {
      model_name: string;
      start_date?: string;
      end_date?: string;
      config_path?: string;
      use_existing_artifacts?: boolean;
    }
  ) => apiClient.post<PredictionJob>(`/api/v1/cases/${caseId}/run`, payload),

  // Diagnosis & scenario & playbook
  diagnostics: (scope: ArtifactScope = {}) =>
    apiClient.get<DiagnosticsPayload & { provenance?: Provenance }>("/api/v1/diagnostics", scope),
  scenarioTriage: (scope: ArtifactScope = {}) =>
    apiClient.get<ScenarioTriagePayload & { provenance?: Provenance }>(
      "/api/v1/scenario-triage",
      scope
    ),
  responsePlaybook: (scope: ArtifactScope = {}) =>
    apiClient.get<PlaybookPayload & { provenance?: Provenance }>(
      "/api/v1/response-playbook",
      scope
    ),

  // Thresholds & boundary
  thresholds: (params: { feature?: string } & ArtifactScope = {}) =>
    apiClient.get<ThresholdsPayload & { provenance?: Provenance }>("/api/v1/thresholds", params),
  boundary: (scope: ArtifactScope = {}) =>
    apiClient.get<BoundarySummary & { provenance?: Provenance }>("/api/v1/boundary", scope),

  // Sensitivity / counterfactual
  sensitivity: (scope: ArtifactScope = {}) =>
    apiClient.get<SensitivityPayload & { provenance?: Provenance }>("/api/v1/sensitivity", scope),

  // Realtime validation
  realtimeValidation: () =>
    apiClient.get<RealtimeValidation>("/api/v1/realtime-validation"),

  // Report export
  exportReport: (format: ReportFormat, scope: ArtifactScope = {}) =>
    apiClient.post<ReportExportResult & { provenance?: Provenance }>(
      "/api/v1/report/export",
      undefined,
      { format, ...scope }
    ),

  // Model registry — governed, versioned models (review item 11).
  models: (params?: { model_key?: string; stage?: string }) =>
    apiClient.get<ModelVersion[]>("/api/v1/models", params),
  modelSummary: () => apiClient.get<ModelSummary>("/api/v1/models/summary"),
  currentModel: (modelKey?: string) =>
    apiClient.get<ModelVersion | null>("/api/v1/models/current", { model_key: modelKey }),
  registerModel: (payload: {
    model_key: string;
    version: string;
    station_code?: string;
    training_dataset_version_id?: string;
    config_hash?: string;
    metrics?: Record<string, unknown>;
    notes?: string;
  }) => apiClient.post<ModelVersion>("/api/v1/models", payload),
  transitionModel: (modelVersionId: string, to_stage: string) =>
    apiClient.post<ModelVersion>(`/api/v1/models/${modelVersionId}/transition`, { to_stage }),

  // Report centre — reports as governed business objects (review item 21).
  reports: (params?: { status?: string; case_id?: string; author?: string }) =>
    apiClient.get<ReportRecord[]>("/api/v1/reports", params),
  reportSummary: () => apiClient.get<ReportSummary>("/api/v1/reports/summary"),
  createReport: (payload: {
    title: string;
    project_name?: string;
    case_id?: string;
    format?: string;
    time_range_start?: string;
    time_range_end?: string;
    content_selection?: string[];
  }) => apiClient.post<ReportRecord>("/api/v1/reports", payload),
  report: (reportId: string) => apiClient.get<ReportRecord>(`/api/v1/reports/${reportId}`),
  submitReport: (reportId: string) =>
    apiClient.post<ReportRecord>(`/api/v1/reports/${reportId}/submit`),
  reviewReport: (reportId: string, approve: boolean, comment?: string) =>
    apiClient.post<ReportRecord>(`/api/v1/reports/${reportId}/review`, { approve, comment }),
  generateReport: (reportId: string) =>
    apiClient.post<ReportRecord>(`/api/v1/reports/${reportId}/generate`),
  archiveReport: (reportId: string) =>
    apiClient.post<ReportRecord>(`/api/v1/reports/${reportId}/archive`),
  deleteReport: (reportId: string) =>
    apiClient.delete<Record<string, unknown>>(`/api/v1/reports/${reportId}`),

  // Event handling — closed-loop alert triage (review item 27).
  events: (params?: { status?: string; severity?: string; case_id?: string }) =>
    apiClient.get<EventRecord[]>("/api/v1/events", params),
  eventSummary: () => apiClient.get<EventSummary>("/api/v1/events/summary"),
  createEvent: (payload: {
    title: string;
    description: string;
    severity?: string;
    case_id?: string;
    target_date?: string;
    source?: string;
  }) => apiClient.post<EventRecord>("/api/v1/events", payload),
  event: (eventId: string) => apiClient.get<EventRecord>(`/api/v1/events/${eventId}`),
  assignEvent: (eventId: string, assignee: string, note?: string) =>
    apiClient.post<EventRecord>(`/api/v1/events/${eventId}/assign`, {
      to_stage: "assigned",
      assignee,
      note,
    }),
  acknowledgeEvent: (eventId: string) =>
    apiClient.post<EventRecord>(`/api/v1/events/${eventId}/acknowledge`),
  handleEvent: (eventId: string) =>
    apiClient.post<EventRecord>(`/api/v1/events/${eventId}/handle`),
  reviewEvent: (eventId: string) =>
    apiClient.post<EventRecord>(`/api/v1/events/${eventId}/review`),
  closeEvent: (eventId: string, post_mortem: string, note?: string) =>
    apiClient.post<EventRecord>(`/api/v1/events/${eventId}/close`, { post_mortem, note }),
  falsePositiveEvent: (eventId: string, reason: string) =>
    apiClient.post<EventRecord>(`/api/v1/events/${eventId}/false-positive`, { reason }),
  escalateEvent: (eventId: string, note?: string) =>
    apiClient.post<EventRecord>(`/api/v1/events/${eventId}/escalate`, { note }),

  // Knowledge graph
  knowledgeGraph: {
    summary: () => apiClient.get<KnowledgeGraphSummary>("/api/v1/knowledge-graph/summary"),
    upload: (formData: FormData) =>
      apiClient.upload<Record<string, unknown>>("/api/v1/knowledge-graph/upload", formData),
    uploads: () => apiClient.get<KgFileInfo[]>("/api/v1/knowledge-graph/uploads"),
    clearUploads: () =>
      apiClient.post<{ deleted_count: number }>("/api/v1/knowledge-graph/uploads/clear"),
    preprocess: (payload: { files: string[]; write_json?: boolean; keep_captions?: boolean }) =>
      apiClient.post<Record<string, unknown>>("/api/v1/knowledge-graph/preprocess", payload),
    texts: () =>
      apiClient.get<{ txt: KgFileInfo[]; json: KgFileInfo[] }>("/api/v1/knowledge-graph/texts"),
    clearTexts: () =>
      apiClient.post<{ deleted_count: number }>("/api/v1/knowledge-graph/texts/clear"),
    clearKg: () =>
      apiClient.post<{ deleted_count: number }>("/api/v1/knowledge-graph/kg/clear"),
    build: (payload: { files: string[]; max_chars?: number }) =>
      apiClient.post<KgBuildJob>("/api/v1/knowledge-graph/build", payload),
    jobs: () => apiClient.get<KgBuildJob[]>("/api/v1/knowledge-graph/jobs"),
    job: (jobId: string) => apiClient.get<KgBuildJob>(`/api/v1/knowledge-graph/jobs/${jobId}`),
    graph: () => apiClient.get<KgGraphPayload>("/api/v1/knowledge-graph/graph"),
    qa: (question: string) =>
      apiClient.post<KgQaResult>("/api/v1/knowledge-graph/qa", { question }),
    downloadUrl: (name: string) => `/api/v1/knowledge-graph/files/${name}`,
  },
};

export const REPORT_FORMATS: { value: ReportFormat; labelKey: string; extension: string }[] = [
  { value: "html", labelKey: "report.formatHtml", extension: ".html" },
  { value: "md", labelKey: "report.formatMd", extension: ".md" },
  { value: "json", labelKey: "report.formatJson", extension: ".json" },
  { value: "pdf", labelKey: "report.formatPdf", extension: ".pdf" },
];
