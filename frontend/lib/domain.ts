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
