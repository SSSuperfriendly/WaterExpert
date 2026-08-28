/**
 * TypeScript contracts mirroring the FastAPI response shapes of
 * backend/app/services/*. These are kept deliberately loose (many backend
 * payloads are dicts) but typed enough to render safely.
 */

export type RiskBand = "high" | "heightened" | "watch" | "low" | "medium";
export type ScenarioKey =
  | "external_input"
  | "internal_release"
  | "algal_dominant"
  | "chronic_composite";
export type ModelKey =
  | "cmfbe_stgcn"
  | "mscim"
  | "mscim_no_kg"
  | "persistence_baseline"
  | "ridge_window_baseline";
export type ReportFormat = "html" | "md" | "json" | "pdf";

export interface LoginResponse {
  access_token?: string;
  token_type?: string;
  username: string;
  display_name: string;
  role: string;
}

export interface CredentialHint {
  username: string;
  password: string;
}

export interface StationProfile {
  station_code: string;
  station_name: string;
  river: string;
  basin: string;
  longitude: number | string;
  latitude: number | string;
  daily_rows: number;
  date_start: string;
  date_end: string;
  matched_model_rows: number;
  hydrodynamic_reference_station?: string;
}

export interface ModelMetric {
  turbidity_r2?: number;
  turbidity_rmse?: number;
  clearness_r2?: number;
  clearness_rmse?: number;
  self_purification_failure?: { event_rate?: number; mean_predicted_probability?: number };
  turbidity_surge?: { event_rate?: number; mean_predicted_probability?: number };
  critical_transition?: { event_rate?: number; mean_predicted_probability?: number };
  [key: string]: unknown;
}

export interface DashboardPayload {
  product_name?: string;
  algorithm_core?: string;
  data_scope?: string;
  purpose?: string;
  artifact_scope?: string;
  artifact_root?: string;
  station_profile?: StationProfile;
  best_model_summary?: Record<string, unknown>;
  test_models?: Record<string, ModelMetric>;
  threshold_risk_snapshot?: Record<string, unknown>;
  scenario_counts?: Record<string, number>;
  high_priority_days?: ScenarioDay[];
  recommended_agent_queries?: string[];
  guardrails?: string[];
}

export interface ScenarioDay {
  target_date: string;
  primary_scenario: string;
  primary_scenario_label?: string;
  secondary_scenario?: string;
  secondary_scenario_label?: string;
  primary_score?: number;
  secondary_score?: number;
  scenario_confidence?: number;
  risk_band: string;
  predicted_critical_transition_prob?: number;
  predicted_self_purification_failure_prob?: number;
  predicted_turbidity_surge_prob?: number;
  net_process_response?: number;
  runoff_source?: number;
  erosion_source?: number;
  phytoplankton_source?: number;
  flushing_sink?: number;
  purification_sink?: number;
  precipitation_3d?: number;
  precipitation_7d?: number;
  songpu_resuspension_potential?: number;
  songpu_flushing_potential?: number;
  bed_shear_proxy?: number;
  velocity_proxy?: number;
  air_temp?: number;
  evidence_summary?: string;
  [key: string]: unknown;
}

export interface DatabaseSummary {
  total_records?: number;
  total_stations?: number;
  date_start?: string;
  date_end?: string;
  key_indicators?: { key: string; label: string }[];
}

export interface QueryResult {
  filters?: Record<string, unknown>;
  matched_rows?: number;
  returned_rows?: number;
  rows?: Record<string, unknown>[];
  columns?: string[];
  pagination?: {
    page: number;
    page_size: number;
    offset: number;
    total_pages: number;
    has_previous: boolean;
    has_next: boolean;
    showing_from: number;
    showing_to: number;
  };
  summary?: {
    station_count?: number;
    date_start?: string;
    date_end?: string;
    mean_turbidity?: number;
    mean_secchi_depth?: number;
  };
}

export interface PreprocessSummary {
  station?: string;
  rows_analyzed?: number;
  date_start?: string;
  date_end?: string;
  total_missing_cells?: number;
  total_outlier_flags?: number;
  feature_profiles?: {
    feature: string;
    feature_label?: string;
    missing?: number;
    missing_rate?: number;
    outliers?: number;
    completeness?: number;
    [key: string]: unknown;
  }[];
  recommendations?: string[];
}

export interface VisualizationPayload {
  station?: string;
  indicator?: string;
  indicator_label?: string;
  series?: { date: string; value: number }[];
  stats?: {
    mean?: number;
    min?: number;
    max?: number;
    latest?: number;
    delta?: number;
  };
  correlations?: { indicator: string; label?: string; value: number }[];
  available_indicators?: { key: string; label: string }[];
}

export interface PredictionJob {
  job_id: string;
  mode: string;
  model_name: string;
  station_code?: string;
  start_date?: string;
  end_date?: string;
  status: string;
  progress?: number;
  created_at?: string;
  completed_at?: string;
  [key: string]: unknown;
}

export interface PredictionSeriesRow {
  target_date: string;
  actual_turbidity?: number;
  predicted_turbidity?: number;
  actual_clearness?: number;
  predicted_clearness?: number;
  predicted_self_purification_failure_prob?: number;
  predicted_turbidity_surge_prob?: number;
  predicted_critical_transition_prob?: number;
  predicted_boundary_probability?: number;
  velocity_proxy?: number;
  bed_shear_proxy?: number;
  erosion_source?: number;
  runoff_source?: number;
  phytoplankton_source?: number;
  flushing_sink?: number;
  purification_sink?: number;
  [key: string]: unknown;
}

export interface PredictionsPayload {
  available_models?: string[];
  available_splits?: string[];
  selected_model?: string;
  selected_split?: string;
  summary?: Record<string, unknown>;
  model_comparison?: Record<string, unknown>[];
  series?: PredictionSeriesRow[];
}

export interface FactorDiagnosis {
  feature: string;
  feature_label?: string;
  driver_score?: number;
  inhibitor_score?: number;
  [key: string]: unknown;
}

export interface DomainDiagnosis {
  direction?: string;
  domain?: string;
  domain_label?: string;
  score?: number;
  [key: string]: unknown;
}

export interface DiagnosticsPayload {
  factor_summary?: Record<string, unknown>;
  process_decomposition?: Record<string, unknown>[];
  domain_diagnosis?: DomainDiagnosis[];
  top_driver_features?: FactorDiagnosis[];
  top_inhibitor_features?: FactorDiagnosis[];
  top_driver_domains?: DomainDiagnosis[];
  top_inhibitor_domains?: DomainDiagnosis[];
}

export interface ThresholdNode {
  node_id?: string;
  type?: string;
  feature?: string;
  agent_label?: string;
  threshold?: number | string;
  unit?: string;
  response?: string;
  r2_gain?: number;
  piecewise_r2?: number;
  response_jump?: number;
  interpretation?: string;
  context_type?: string;
  context?: string;
  [key: string]: unknown;
}

export interface ThresholdsPayload {
  threshold_semantics?: string;
  risk_snapshot?: Record<string, unknown>;
  summary?: Record<string, unknown>[];
  by_context?: Record<string, unknown>;
  knowledge_graph?: Record<string, unknown>;
  threshold_nodes?: ThresholdNode[];
  contextual_threshold_nodes?: ThresholdNode[];
}

export interface BoundarySummary {
  summary?: Record<string, unknown>;
  label_generation_summary?: Record<string, unknown>;
  prediction_preview?: Record<string, unknown>[];
  models?: Record<string, Record<string, Record<string, number>>>;
  overall?: Record<string, Record<string, number>>;
  status?: string;
}

export interface ScenarioTriagePayload {
  threshold_semantics?: string;
  classification_semantics?: string;
  scenario_definitions?: Record<string, unknown>;
  thresholds_used?: Record<string, unknown>;
  test_window_start?: string;
  test_window_end?: string;
  scenario_counts?: Record<string, number>;
  mean_primary_scores_by_scenario?: Record<string, number>;
  high_priority_days?: ScenarioDay[];
  daily_records?: ScenarioDay[];
  guardrails?: string[];
}

export interface PlaybookPayload {
  scenario_response_playbook?: Record<string, unknown>;
  prioritized_cases?: Record<string, unknown>[];
  threshold_digest?: Record<string, unknown>[];
  guardrails?: string[];
  future_extensions?: unknown;
}

export interface SobolFactor {
  factor?: string;
  factor_label?: string;
  lower_bound?: number;
  upper_bound?: number;
  first_order_index?: number;
  total_order_index?: number;
  interaction_strength?: number;
  [key: string]: unknown;
}

export interface SensitivityPayload {
  sobol?: {
    status?: string;
    sample_count?: number;
    response?: string;
    top_factors?: SobolFactor[];
  };
  counterfactual?: Record<string, unknown>[];
  joint_counterfactual?: Record<string, unknown>[];
}

export interface RealtimeValidation {
  status: "missing" | "error" | "ok";
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ReportExportResult {
  report_path: string;
  filename: string;
  format: string;
  download_url: string;
}

export interface KgFileInfo {
  name: string;
  size_bytes?: number;
}

export interface KnowledgeGraphSummary {
  uploads?: number;
  texts?: number;
  node_count?: number;
  edge_count?: number;
  source?: "runtime" | "baseline" | "none";
  llm_configured?: boolean;
}

export interface KgGraphNode {
  id: string;
  label?: string;
  type?: string;
}

export interface KgGraphEdge {
  source: string;
  target: string;
  relation?: string;
  evidence?: string;
}

export interface KgGraphPayload {
  nodes: KgGraphNode[];
  edges: KgGraphEdge[];
  node_count: number;
  edge_count: number;
  source: string;
}

export interface KgMatchedRelation {
  source?: string;
  source_type?: string;
  relation?: string;
  target?: string;
  target_type?: string;
  evidence?: string;
  source_file?: string;
  _score?: number;
  [key: string]: unknown;
}

export interface KgQaResult {
  question: string;
  answer: string;
  matched_relations: KgMatchedRelation[];
  source: string;
}

export interface KgBuildJob {
  job_id: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  files?: string[];
  max_chars?: number;
  status: string;
  progress?: number;
  current_file?: string;
  relation_count?: number;
  message?: string;
  error?: string;
  [key: string]: unknown;
}
