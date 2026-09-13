/**
 * TypeScript contracts mirroring the FastAPI response shapes of
 * backend/app/services/*. These are kept deliberately loose (many backend
 * payloads are dicts) but typed enough to render safely.
 */

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

/** The caller's own profile (personal centre, ``/api/v1/users/me``). */
export interface UserProfile {
  id: string;
  username: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  /** True when the account holds a usable password. OAuth-only accounts keep it
   * false until the holder sets a first password; the UI switches between the
   * "设置密码" flow and the password-gated username/email/password edits on it. */
  has_password: boolean;
  /** Linked identity providers, e.g. ``["github"]``. */
  oauth_providers: string[];
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

/**
 * The data asset centre. A dataset groups versions of the same feed; a version
 * is one accepted-or-rejected pass through the ingestion chain.
 *
 * `quality_grade` is "a" | "b" | "c" | "d" and `modelable` is "1" | "0" — both
 * are stable codes the UI localises, never display strings.
 */
export interface Dataset {
  dataset_id: string;
  title?: string;
  data_type: string;
  station_code?: string;
  owner?: string;
  status: string;
  version_count?: number;
  latest_accepted_version_id?: string | null;
  coverage_start?: string | null;
  coverage_end?: string | null;
  quality_grade?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface DatasetVersion {
  version_id: string;
  dataset_id: string;
  version: string;
  data_type?: string;
  status: string;
  /** The chain stage reached; on a rejection this is where it stopped. */
  stage: string;
  blocked_at?: string | null;
  blocking_reasons?: string[];
  quality_grade?: string;
  modelable?: string;
  source_name?: string;
  source_kind?: string;
  row_count?: number;
  modelable_rows?: number;
  coverage_start?: string | null;
  coverage_end?: string | null;
  station_coverage?: string[];
  created_at?: string;
  [key: string]: unknown;
}

export interface DatasetStageReport {
  stage: string;
  ok: boolean;
  metrics?: Record<string, unknown>;
  errors?: string[];
}

export interface DatasetQualityReport {
  version_id?: string;
  final_stage: string;
  stages: DatasetStageReport[];
  grade?: string;
  missing_rate?: number;
  duplicate_rows?: number;
  out_of_range_count?: number;
  modelable_rows?: number;
  blocking_reasons?: string[];
  unit_conversions?: { field: string; from: string; to: string; factor: number }[];
  [key: string]: unknown;
}

export interface DatasetPreview {
  available: boolean;
  /** Present only when `available` is false: the stage that blocked it. */
  reason?: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
}

export interface DatasetFreshness {
  dataset_count: number;
  modelable_count: number;
  latest_coverage_end?: string | null;
  is_stale: boolean;
  stale_after_days?: number;
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

/** What the pipeline actually applied, as written to `metrics/run_scope.json`. */
export interface EffectiveJobParameters {
  models?: string[];
  station_code?: string;
  requested_start_date?: string | null;
  requested_end_date?: string | null;
  effective_start_date?: string;
  effective_end_date?: string;
  rows_before_scope?: number;
  rows_after_scope?: number;
  applied?: boolean;
}

export interface PredictionJob {
  job_id: string;
  model_name: string;
  station_code?: string;
  start_date?: string;
  end_date?: string;
  status: string;
  progress?: number;
  priority?: number;
  stage?: string;
  elapsed_seconds?: number;
  estimated_remaining_seconds?: number;
  failure_category?: string;
  created_at?: string;
  queued_at?: string;
  started_at?: string;
  finished_at?: string;
  completed_at?: string;
  requested_parameters?: Record<string, unknown>;
  effective_parameters?: EffectiveJobParameters;
  [key: string]: unknown;
}

export interface JobQueueSnapshot {
  max_concurrent_jobs: number;
  running: number;
  queued: number;
  free_slots: number;
  by_status: Record<string, number>;
  job_timeout_seconds: number;
}

export interface JobArtifact {
  relative_path: string;
  size_bytes: number;
  category: string;
}

/** The version stamp every result payload carries (review item 5). */
export interface Provenance {
  case_id: string | null;
  run_id: string | null;
  job_id: string | null;
  generated_at: string | null;
  model_version: string | null;
  config_hash: string | null;
  is_stale: boolean;
  stale_reason: string | null;
  scope: "case" | "job" | "integrated";
  is_integrated_default?: boolean;
}

export interface Case {
  case_id: string;
  title: string;
  description?: string;
  owner: string;
  status: string;
  station_code?: string;
  target_date?: string;
  input_dataset_versions: string[];
  data_quality?: Record<string, unknown>;
  coverage_start?: string | null;
  coverage_end?: string | null;
  job_id?: string | null;
  run_id?: string | null;
  config_hash?: string | null;
  model_version?: string | null;
  report_ids: string[];
  artifacts_generated_at?: string | null;
  is_stale?: boolean;
  stale_reason?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface CaseSummary {
  total: number;
  by_status: Record<string, number>;
  stale_count: number;
  pending_count: number;
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
  /** Which graph the edge came from — ``platform`` or ``inherited``. */
  source_id?: string;
  relation?: string;
  target?: string;
  target_type?: string;
  evidence?: string;
  source_file?: string;
  _score?: number;
  [key: string]: unknown;
}

/** One retrieval path: a chain of nodes and the edges that connect them. */
export interface KgQaPath {
  path_id?: string;
  source_id?: string;
  nodes: string[];
  edges?: Array<{
    source: string;
    source_id?: string;
    relation?: string;
    target: string;
    evidence?: string;
    source_file?: string;
  }>;
  hops?: number;
  score?: number;
  score_parts?: Record<string, number>;
}

export interface KgQaCitation {
  marker: string;
  kind: "relation" | "chunk" | "community" | string;
  source_id?: string;
  source?: string;
  relation?: string;
  target?: string;
  evidence?: string;
  source_file?: string;
  chunk_id?: string | null;
  community_id?: string;
}

export interface KgQaCommunity {
  community_id: string;
  source_id?: string;
  size?: number;
  summary?: string;
  summary_mode?: string;
  top_nodes?: string[];
  score?: number;
}

export interface KgQaSeed {
  name: string;
  score?: number;
  matched_via?: string;
  surface?: string;
  entity_type?: string;
  source_id?: string;
}

export interface KgQaSourceInfo {
  source_id: string;
  label: string;
  /** The i18n key for ``label`` — the backend's own, not one the UI guesses. */
  label_key?: string;
  provenance?: string;
  relation_count?: number;
  node_count?: number;
  chunk_level?: boolean;
}

/** A chunk of source text, present only where the index has chunk provenance. */
export interface KgQaChunk {
  chunk_id: string;
  excerpt: string;
  source_file?: string;
  ordinal?: number;
  truncated?: boolean;
  used_by_relations?: string[][];
}

/**
 * One drawable node of a retrieved subgraph.
 *
 * ``id`` is the namespaced key (``platform::浊度``) and is the only identity the
 * canvas uses: it is what a request round-trips, what an edge names as its
 * endpoints, and what a highlight matches on. The two graphs are namespaced
 * precisely because a bare name is ambiguous between them.
 */
export interface KgSubgraphNode {
  id: string;
  name: string;
  source_id: string;
  type?: string;
  degree?: number;
}

/**
 * One drawable edge.
 *
 * ``id`` is unique per parallel edge — two relations between the same ordered
 * pair get different ids — because ``vis.DataSet`` keys on it, and a collision
 * silently drops a relation the answer cited.
 */
export interface KgSubgraphEdge {
  id: string;
  source_id: string;
  source: string;
  target: string;
  display_source: string;
  display_target: string;
  relation?: string;
  evidence?: string;
  source_file?: string;
  chunk_id?: string | null;
}

/**
 * The canvas's answer to "draw what this question found".
 *
 * Referentially complete by construction: every edge endpoint appears in
 * ``nodes``. ``missing`` and ``truncated`` are the honest edges of the
 * response — an entity that could not be found and a cap that bit — reported
 * rather than silently dropped, because a silently short subgraph looks exactly
 * like a complete one.
 */
export interface KgSubgraph {
  nodes: KgSubgraphNode[];
  edges: KgSubgraphEdge[];
  sources?: KgQaSourceInfo[];
  missing?: Array<{ source_id: string; name: string }>;
  unresolved_communities?: string[];
  truncated?: boolean;
  focus_edge_id?: string | null;
}

/**
 * The GraphRAG QA response.
 *
 * The first four keys are the pre-GraphRAG contract, unchanged in name, type
 * and meaning — every consumer written before the graph search existed still
 * works. Everything below them is additive, so an older platform that does not
 * send them renders the same page it always did.
 */
export interface KgQaResult {
  question: string;
  answer: string;
  matched_relations: KgMatchedRelation[];
  source: string;

  mode?: "local" | "global" | "hybrid" | "none";
  graph_rag_version?: string;
  capabilities?: { chunk_level?: boolean; communities?: boolean; citations?: boolean };
  sources?: KgQaSourceInfo[];
  paths?: KgQaPath[];
  chunks?: KgQaChunk[];
  communities?: KgQaCommunity[];
  citations?: KgQaCitation[];
  seed_entities?: KgQaSeed[];
  stats?: {
    relation_count?: number;
    path_count?: number;
    seed_count?: number;
    elapsed_ms?: number;
    llm_called?: boolean;
    degraded?: boolean;
    citation_validity?: number;
    groundedness?: number;
    hallucinated_markers?: string[];
    notes?: string[];
  };
}

/** Externally deployed WaterExpert agent API (docs/internal/INTEGRATION_GUIDE.md). */
export interface AgentHealth {
  status?: string;
  timestamp?: string;
  agents?: Record<string, string>;
  [key: string]: unknown;
}

export interface AgentScenario {
  code: string;
  name: string;
  description?: string;
  [key: string]: unknown;
}

export interface AgentStrategyState {
  date: string;
  turbidity: number;
  flow_rate: number;
  temperature?: number;
  ph?: number;
  dissolved_oxygen?: number;
  chlorophyll_a?: number;
  rainfall_3d?: number;
  rainfall_7d?: number;
  [key: string]: unknown;
}

export interface AgentStrategyRequest {
  scenario: string;
  state: AgentStrategyState;
  episodes?: number;
  backend?: string;
}

export interface AgentStrategyJob {
  job_id: string;
  status: string;
  scenario?: string;
  created_at?: string;
  message?: string;
  error?: string;
  [key: string]: unknown;
}

/** One factor MSCIM attributed the predicted turbidity to. */
export interface AgentMscimDriver {
  factor?: string;
  importance?: number;
  /** Absent on the rule-based path, which scores factors without reading them. */
  value?: number;
  threshold_exceeded?: boolean;
  [key: string]: unknown;
}

/**
 * MSCIM's diagnosis, or the reason there isn't one.
 *
 * ``inference_source`` is the field that decides how the rest may be read.
 * ``"checkpoint"`` means the trained model produced these numbers;
 * ``"fallback_rules"`` means it did not load and a rule of thumb did — with
 * ``checkpoint_error`` saying why. The two render identically otherwise, which
 * is how a degraded run passed for a prediction.
 */
export interface AgentMscimTrace {
  model?: string;
  checkpoint_path?: string;
  inference_source?: "checkpoint" | "fallback_rules" | string;
  checkpoint_error?: string;
  /** Present when the model threw; the trace then carries no prediction. */
  error?: string;
  prediction?: {
    turbidity?: number;
    turbidity_confidence?: number;
    clearness_proxy?: number;
    log_turbidity?: number;
    [key: string]: unknown;
  };
  diagnosis?: {
    primary_drivers?: AgentMscimDriver[];
    dominant_driver?: AgentMscimDriver | null;
    uncertainty?: { epistemic?: number; aleatoric?: number; [key: string]: unknown };
    model_signals?: Record<string, number>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

/**
 * A critical level the current state is above, and the fit that justifies it.
 *
 * `r2_gain` and `response_jump` are the evidence that this value is a threshold
 * rather than a percentile: how much of the response variance the split
 * explains, and how far the response moves across it. They come from the
 * threshold graph, so they are null when the platform did not send one.
 */
export interface AgentThresholdBreach {
  /** The graph's feature name — e.g. `precipitation_3d`. */
  factor?: string;
  value?: number;
  threshold?: number;
  unit?: string;
  /** The graph's own wording for the feature, in English. */
  label?: string;
  r2_gain?: number | null;
  piecewise_r2?: number | null;
  response_jump?: number | null;
  interpretation?: string;
  [key: string]: unknown;
}

/** Which physical processes CMFBE credited, and which it debited. */
export interface AgentCmfbeTrace {
  model?: string;
  checkpoint_path?: string;
  inference_source?: "checkpoint" | "fallback_rules" | string;
  checkpoint_error?: string;
  error?: string;
  process_decomposition?: Record<string, number>;
  net_change?: number;
  /** The levels screened against, by graph feature name. Empty when none were sent. */
  thresholds?: Record<string, number>;
  /**
   * Where the levels came from. `unavailable` means the platform sent none, so
   * an empty `threshold_breaches` is "nothing was screened" rather than "clear".
   */
  threshold_source?: "knowledge_graph" | "unavailable" | string;
  threshold_breaches?: AgentThresholdBreach[];
  predictions?: {
    next_day_turbidity?: number;
    physics_turbidity?: number;
    clearness_proxy?: number;
    next_day_turbidity_trend?: string;
    confidence?: number;
    [key: string]: unknown;
  };
  physics?: Record<string, number>;
  [key: string]: unknown;
}

/**
 * A candidate technique, and what its number rests on.
 *
 * ``origin`` is what a reader has to branch on. ``"scenario"`` means the
 * platform's own technique vocabulary, priced off the case named by ``case_id``
 * — which is where ``intensity``, ``intensity_unit`` and ``reference`` come
 * from. ``"graph"`` means a retrieved edge: a real influence recorded in one of
 * the graphs, with no dose attached to it, which is why every parameter is
 * ``null`` there. ``"seed"`` is the curated technology table, used only for a
 * scenario the vocabulary does not cover.
 */
export interface AgentKbRecommendation {
  technique?: string;
  origin?: "graph" | "scenario" | "seed" | string;
  intensity?: number | null;
  intensity_unit?: string | null;
  intensity_field?: string | null;
  cost_per_day?: number | null;
  case_id?: string | null;
  case_similarity?: number | null;
  reference?: string;
  /** Which graph, under the name the platform shows for it. Graphs only. */
  source_label?: string;
  source_id?: string;
  relation?: string;
  evidence?: string;
  citation?: string;
  environment?: string;
  effect?: string;
  [key: string]: unknown;
}

/** A published case, with the intervention and the outcome it reported. */
export interface AgentCaseEvidence {
  id?: string;
  title?: string;
  location?: string;
  year?: number;
  scenario?: string;
  similarity?: number;
  summary?: string;
  reference?: string;
  intervention?: Record<string, number>;
  outcome?: {
    turbidity_reduction_ratio?: number;
    cost_saving_ratio?: number;
    recovery_days?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

/** What each of the six agents was given and what it did with it. */
export interface AgentTraces {
  mscim?: AgentMscimTrace;
  cmfbe?: AgentCmfbeTrace;
  kb?: {
    input?: Record<string, unknown>;
    output?: {
      source?: string;
      grounded?: boolean;
      graph_mode?: string;
      graph_query?: string;
      recommendations?: AgentKbRecommendation[];
      case_evidence?: AgentCaseEvidence[];
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  gpt?: { input?: Record<string, unknown>; output?: Record<string, unknown>; [key: string]: unknown };
  rl?: { input?: Record<string, unknown>; output?: Record<string, unknown>; [key: string]: unknown };
  safety?: { input?: Record<string, unknown>; output?: Record<string, unknown>; [key: string]: unknown };
  [key: string]: unknown;
}

export interface AgentStrategyResult {
  job_id: string;
  status: string;
  scenario?: string;
  strategy?: {
    release_rate: number;
    aeration_intensity: number;
    chemical_dosage: number;
    [key: string]: unknown;
  };
  metrics?: {
    turbidity_reduction: number;
    turbidity_reduction_ratio: number;
    energy_cost: number;
    cost_saving_ratio: number;
    stability: number;
    response_time_hours: number;
    [key: string]: unknown;
  };
  /** The per-agent reasoning behind the strategy above. */
  agent_traces?: AgentTraces;
  completed_at?: string;
  error?: string;
  [key: string]: unknown;
}

/** A matched historical case returned by the explain endpoint. */
export interface AgentMatchedCase {
  id?: string;
  title?: string;
  location?: string;
  year?: number;
  similarity?: number;
  summary?: string;
  reference?: string;
  outcome?: {
    turbidity_reduction_ratio?: number;
    cost_saving_ratio?: number;
    recovery_days?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

/** Narrative diagnosis + matched cases for a state under a scenario. */
export interface AgentExplainResult {
  scenario?: string;
  explanation?: string;
  matched_cases?: AgentMatchedCase[];
  [key: string]: unknown;
}

export interface AgentExplainRequest {
  scenario: string;
  state: AgentStrategyState;
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

/** A model-registry entry (review item 11). */
export interface ModelVersion {
  model_version_id: string;
  model_key: string;
  version: string;
  stage: string;
  station_code?: string | null;
  training_dataset_version_id?: string | null;
  config_hash?: string | null;
  metrics?: Record<string, unknown>;
  author?: string | null;
  notes?: string | null;
  published_at?: string | null;
  published_by?: string | null;
  retired_at?: string | null;
  retired_by?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ModelSummary {
  total: number;
  by_stage: Record<string, number>;
  published: number;
  current_by_key: Record<string, string>;
}

/** A report as a governed business object (review item 21). */
export interface ReportRecord {
  report_id: string;
  title: string;
  status: string;
  author?: string | null;
  reviewer?: string | null;
  project_name?: string | null;
  case_id?: string | null;
  format?: string;
  version?: number;
  file_path?: string | null;
  filename?: string | null;
  download_url?: string | null;
  time_range_start?: string | null;
  time_range_end?: string | null;
  content_selection?: string[];
  review_comment?: string | null;
  reviewed_at?: string | null;
  generated_at?: string | null;
  archived_at?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ReportSummary {
  total: number;
  by_status: Record<string, number>;
  pending_review: number;
}

/** An alert/event with a closed-loop state machine (review item 27). */
export interface EventRecord {
  event_id: string;
  title: string;
  description: string;
  status: string;
  severity: string;
  source?: string;
  case_id?: string | null;
  target_date?: string | null;
  assignee?: string | null;
  creator?: string | null;
  escalated?: boolean;
  post_mortem?: string | null;
  history?: { status: string; at?: string; by?: string | null; note?: string | null }[];
  acknowledged_at?: string | null;
  closed_at?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface EventSummary {
  total: number;
  open: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
}

/**
 * The deployment's structured vocabulary (GET /api/v1/capabilities). Selectors
 * are built from this so the frontend never hard-codes what the backend
 * supports.
 */
export interface CapabilityOption {
  key: string;
  label?: string;
  label_code?: string;
  required?: boolean;
  derived?: boolean;
}

export interface CapabilityStation {
  station_code?: string;
  station_name?: string;
  [key: string]: unknown;
}

export interface Capabilities {
  data_types: CapabilityOption[];
  models: CapabilityOption[];
  severities: string[];
  report_formats: string[];
  model_stages: string[];
  model_transitions: Record<string, string[]>;
  indicators: CapabilityOption[];
  stations: CapabilityStation[];
}

/**
 * The Zhangjiabang cross-modal satellite view: UAV assets (images and videos
 * sliced into representative frames), the fused daily table and the model
 * comparison. Every field comes from the processed artifacts on disk.
 */
export interface CrossModalAsset {
  asset_id?: string;
  sample_date?: string;
  sample_site_role?: string;
  media_type?: string;
  file_name?: string;
  file_size_bytes?: number;
  preview_url?: string;
  representative_frames?: string[];
  frame_count?: number;
  fps?: number;
  duration_seconds?: number;
  turbidity_visual_proxy?: number;
  sharpness_laplacian?: number;
  visual_transformer_embedding_norm?: number;
  visual_transformer_embed_dim?: number;
  [key: string]: unknown;
}

export interface CrossModalSummary {
  generated_at?: string;
  site?: string;
  modality_status?: Record<string, string>;
  counts?: Record<string, number>;
  date_ranges?: Record<string, { start?: string; end?: string }>;
  supervised_dates?: string[];
  preview_assets?: CrossModalAsset[];
  daily_rows?: Record<string, unknown>[];
  model_evaluation?: Record<string, unknown> | null;
  [key: string]: unknown;
}
