"use client";

import { apiClient } from "./client";
import type {
  BoundarySummary,
  CredentialHint,
  DashboardPayload,
  DatabaseSummary,
  DiagnosticsPayload,
  LoginResponse,
  PredictionsPayload,
  PredictionJob,
  PreprocessSummary,
  QueryResult,
  RealtimeValidation,
  ReportExportResult,
  ScenarioTriagePayload,
  SensitivityPayload,
  ThresholdsPayload,
  VisualizationPayload,
  ReportFormat,
  PlaybookPayload,
} from "./contracts";

export const endpoints = {
  // Auth
  login: (username: string, password: string) =>
    apiClient.post<LoginResponse>("/api/v1/auth/login", { username, password }),
  credentialHint: () => apiClient.get<CredentialHint>("/api/v1/auth/hint"),

  // Meta & overview
  meta: () => apiClient.get<Record<string, unknown>>("/api/v1/meta"),
  dashboard: () => apiClient.get<DashboardPayload>("/api/v1/dashboard"),
  stations: () => apiClient.get<Record<string, unknown>>("/api/v1/stations"),

  // Database
  databaseSummary: () => apiClient.get<DatabaseSummary>("/api/v1/database/summary"),
  databaseStations: () => apiClient.get<Record<string, unknown>>("/api/v1/database/stations"),
  query: (params: Record<string, string | number | undefined>) =>
    apiClient.get<QueryResult>("/api/v1/database/query", params),

  // Import / upload
  importData: (payload: {
    data_type: string;
    source_name: string;
    file_path: string;
    time_granularity?: string;
    station_code?: string;
  }) => apiClient.post<Record<string, unknown>>("/api/v1/data/import", payload),
  uploadData: (formData: FormData) =>
    apiClient.upload<Record<string, unknown>>("/api/v1/data/upload", formData),
  imports: () => apiClient.get<Record<string, unknown>[]>("/api/v1/data/imports"),

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
    mode: string;
    model_name: string;
    station_code?: string;
    start_date?: string;
    end_date?: string;
    use_existing_artifacts?: boolean;
  }) => apiClient.post<PredictionJob>("/api/v1/prediction-jobs", payload),
  jobs: () => apiClient.get<PredictionJob[]>("/api/v1/prediction-jobs"),
  job: (jobId: string) => apiClient.get<PredictionJob>(`/api/v1/prediction-jobs/${jobId}`),
  jobSeries: (jobId: string) =>
    apiClient.get<unknown>(`/api/v1/prediction-jobs/${jobId}/series`),
  predictions: (params: { model?: string; split?: string; job_id?: string }) =>
    apiClient.get<PredictionsPayload>("/api/v1/predictions", params),

  // Diagnosis & scenario & playbook
  diagnostics: () => apiClient.get<DiagnosticsPayload>("/api/v1/diagnostics"),
  scenarioTriage: () => apiClient.get<ScenarioTriagePayload>("/api/v1/scenario-triage"),
  responsePlaybook: () => apiClient.get<PlaybookPayload>("/api/v1/response-playbook"),

  // Thresholds & boundary
  thresholds: (params: { feature?: string; job_id?: string }) =>
    apiClient.get<ThresholdsPayload>("/api/v1/thresholds", params),
  boundary: () => apiClient.get<BoundarySummary>("/api/v1/boundary"),

  // Sensitivity / counterfactual
  sensitivity: () => apiClient.get<SensitivityPayload>("/api/v1/sensitivity"),

  // Realtime validation
  realtimeValidation: () =>
    apiClient.get<RealtimeValidation>("/api/v1/realtime-validation"),

  // Report export
  exportReport: (format: ReportFormat, jobId?: string) =>
    apiClient.post<ReportExportResult>("/api/v1/report/export", undefined, {
      format,
      job_id: jobId || undefined,
    }),
};

export const REPORT_FORMATS: { value: ReportFormat; labelKey: string; extension: string }[] = [
  { value: "html", labelKey: "report.formatHtml", extension: ".html" },
  { value: "md", labelKey: "report.formatMd", extension: ".md" },
  { value: "json", labelKey: "report.formatJson", extension: ".json" },
  { value: "pdf", labelKey: "report.formatPdf", extension: ".pdf" },
];
