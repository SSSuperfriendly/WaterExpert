"use client";

/**
 * Pure domain helpers for translating backend enum keys into localized labels.
 * The `t` function is injected so these stay usable outside of React render
 * (they are called from components that already hold a `t`).
 */

type T = (key: string, vars?: Record<string, string | number>) => string;

export function translateScenario(t: T, key: string | undefined | null, fallback?: string): string {
  if (!key) return fallback ?? "—";
  const localized = t(`enums.scenario.${key}`);
  return localized.startsWith("enums.") ? fallback ?? key : localized;
}

export function translateRisk(t: T, key: string | undefined | null, fallback?: string): string {
  if (!key) return fallback ?? "—";
  const localized = t(`enums.risk.${key}`);
  return localized.startsWith("enums.") ? fallback ?? key : localized;
}

export function translateModel(t: T, key: string | undefined | null): string {
  if (!key) return "—";
  const localized = t(`enums.model.${key}`);
  return localized.startsWith("enums.") ? key : localized;
}

export function translateIndicator(t: T, key: string | undefined | null, fallback?: string): string {
  if (!key) return fallback ?? "—";
  const localized = t(`enums.indicator.${key}`);
  return localized.startsWith("enums.") ? fallback ?? key : localized;
}

export function translateFactor(t: T, key: string | undefined | null, fallback?: string): string {
  if (!key) return fallback ?? "—";
  const localized = t(`enums.factor.${key}`);
  return localized.startsWith("enums.") ? fallback ?? key : localized;
}

export function translateProcess(t: T, key: string | undefined | null): string {
  if (!key) return "—";
  const localized = t(`enums.process.${key}`);
  return localized.startsWith("enums.") ? key : localized;
}

export function translateDomain(t: T, key: string | undefined | null, fallback?: string): string {
  if (!key) return fallback ?? "—";
  const localized = t(`enums.domain.${key}`);
  return localized.startsWith("enums.") ? fallback ?? key : localized;
}

export function translateRole(t: T, key: string | undefined | null): string {
  if (!key) return "—";
  const localized = t(`roles.${key}`);
  return localized.startsWith("roles.") ? key : localized;
}

/** Resolve `namespace.key`, falling back to the raw key when untranslated. */
function translateEnum(t: T, namespace: string, key: string | undefined | null): string {
  if (!key) return "—";
  const localized = t(`${namespace}.${key}`);
  return localized.startsWith(`${namespace}.`) ? key : localized;
}

/** Data quality grade A–D. Only A and B are modelable. */
export function translateQualityGrade(t: T, grade: string | undefined | null): string {
  return translateEnum(t, "quality.grade", grade);
}

/** Where a knowledge-graph result was drawn from: runtime / baseline / none. */
export function translateKgSource(t: T, source: string | undefined | null): string {
  return translateEnum(t, "kg.source", source);
}

/** Model-evaluation split: train / valid / test. */
export function translateSplit(t: T, split: string | undefined | null): string {
  return translateEnum(t, "enums.split", split);
}

/**
 * Arbitrary tabular column header → localized label. Resolves against the
 * shared `columns` data dictionary first, then the `enums.indicator` / `enums.factor`
 * vocabularies, and finally degrades to the raw key (column names that are not
 * modelled stay visible as-is rather than being silently dropped).
 */
export function translateColumn(t: T, key: string | undefined | null): string {
  if (!key) return "—";
  const known = t(`columns.${key}`);
  if (!known.startsWith("columns.")) return known;
  const indicator = t(`enums.indicator.${key}`);
  if (!indicator.startsWith("enums.")) return indicator;
  const factor = t(`enums.factor.${key}`);
  if (!factor.startsWith("enums.")) return factor;
  return key;
}

/** Threshold risk-snapshot metric key → localized label. */
export function translateRiskMetric(t: T, key: string | undefined | null): string {
  return translateEnum(t, "riskMetric", key);
}

/** Job status (queued/running/cancelling/…/orphaned) → localized label. */
export function translateJobStatus(t: T, status: string | undefined | null): string {
  return translateEnum(t, "status", status);
}

/** Why a job failed (config_invalid/data_missing/…) → localized label. */
export function translateFailureCategory(t: T, category: string | undefined | null): string {
  return translateEnum(t, "failure", category);
}

/** Dataset / dataset-version lifecycle status. */
export function translateDatasetStatus(t: T, status: string | undefined | null): string {
  return translateEnum(t, "quality.status", status);
}

/** Model-registry stage (experiment → candidate → in_review → published → retired). */
export function translateModelStage(t: T, stage: string | undefined | null): string {
  return translateEnum(t, "enums.modelStage", stage);
}

/** Report lifecycle status (draft → pending_review → approved/rejected → archived). */
export function translateReportStatus(t: T, status: string | undefined | null): string {
  return translateEnum(t, "enums.reportStatus", status);
}

/** Event state machine (open → assigned → … → closed / false_positive). */
export function translateEventStatus(t: T, status: string | undefined | null): string {
  return translateEnum(t, "enums.eventStatus", status);
}

/** Event severity (info / low / medium / high / critical). */
export function translateSeverity(t: T, severity: string | undefined | null): string {
  return translateEnum(t, "enums.severity", severity);
}

/** A stage of the ingestion chain: uploaded → validated → … → accepted. */
export function translateStage(t: T, stage: string | undefined | null): string {
  return translateEnum(t, "quality.stage", stage);
}

/** Why a dataset version was refused, e.g. `missing_required_fields`. */
export function translateBlockingReason(t: T, reason: string | undefined | null): string {
  // Reasons can carry a `reason:field:detail` payload; the leading token is the
  // translatable part and the rest is data worth keeping visible.
  if (!reason) return "—";
  const [code, ...rest] = reason.split(":");
  const label = translateEnum(t, "quality.reason", code);
  return rest.length ? `${label} (${rest.join(":")})` : label;
}

export function translateDataType(t: T, dataType: string | undefined | null): string {
  return translateEnum(t, "upload", dataType);
}

/**
 * Turn a thrown API error into something a user can read.
 *
 * Review item 22: backend exception strings must never be rendered directly.
 * The API returns `{code, detail}` for refusals it models; `code` drives the
 * localized message and `detail` is dropped (it is written for operators and
 * logs). Anything else degrades to a generic message.
 */
export function describeApiError(t: T, error: unknown): string {
  const code = extractErrorCode(error);
  if (code) {
    const localized = t(`errors.${code}`);
    if (!localized.startsWith("errors.")) return localized;
  }
  return t("common.error");
}

/** The stable `code` from a `{code, detail}` error body, when there is one. */
export function extractErrorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null) return null;
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === "object" && detail !== null) {
    const code = (detail as { code?: unknown }).code;
    if (typeof code === "string") return code;
  }
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

/** Badge variant for a risk band. */
export function riskBadgeVariant(risk: string | undefined | null): "destructive" | "secondary" | "outline" {
  if (risk === "high") return "destructive";
  if (risk === "heightened") return "secondary";
  return "outline";
}

/** Tailwind text color class for a process contribution direction. */
export function processDirectionClass(value: number | undefined | null): string {
  if (value === undefined || value === null) return "text-muted-foreground";
  return value >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
}
