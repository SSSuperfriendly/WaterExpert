/**
 * Domain formatting helpers shared across the WaterExpert frontend.
 * These intentionally mirror the numeric/date formatting of the legacy static
 * frontend so that rendered values remain consistent.
 */

export function formatNumber(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  if (Number.isInteger(n) && Math.abs(n) < 1e6) return n.toLocaleString("en-US");
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(value: unknown, digits = 1): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return `${(n * 100).toFixed(digits)}%`;
}

export function formatMaybeDate(value: unknown): string {
  if (!value) return "—";
  const s = String(value);
  // Already YYYY-MM-DD (or date-time) → take the date part.
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  return s;
}

export function formatDateTime(value: unknown): string {
  if (!value) return "—";
  const s = String(value);
  return s.replace("T", " ").replace(/\.\d+Z?$/, "").slice(0, 19);
}

/** Compact signed delta, e.g. "+0.35" / "-1.20" / "0.00". */
export function formatDelta(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
