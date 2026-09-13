/**
 * The pure decision about how to read a threshold screening.
 *
 * Extracted from the panel for the same reason `focusIds` was extracted from
 * the canvas: it is the part that can be wrong in a way nobody notices, and a
 * decision that only exists inside JSX can only be tested by rendering the
 * component, which this project cannot do.
 *
 * The case that matters is the empty list. `threshold_breaches: []` is what a
 * run reports both when it checked ten levels and found the state below all of
 * them, and when it was handed no levels at all — and those two are opposites.
 * Rendering the second as "no thresholds breached" is a clean bill of health
 * for a run that screened nothing, which is the most dangerous thing this
 * panel could say.
 */

/** What an empty breach list means. */
export type ThresholdVerdict =
  /** Levels were screened against, and the state is below all of them. */
  | "clear"
  /** Levels were screened against, and the state is above at least one. */
  | "breached"
  /** No levels were supplied, so nothing was screened. Not an all-clear. */
  | "unavailable";

/** The sources CMFBE reports. `knowledge_graph` is the platform's threshold graph. */
export const THRESHOLD_SOURCE_GRAPH = "knowledge_graph";

export function thresholdVerdict(
  source: string | undefined,
  breachCount: number,
): ThresholdVerdict {
  // A breach is shown whatever the source is called. It is a warning, and
  // withholding a warning because this build does not recognise the word for
  // where it came from would be the unsafe half of the asymmetry.
  if (breachCount > 0) return "breached";
  // An all-clear is the claim that needs provenance. It is read only from the
  // platform's threshold graph: a run that screened against nothing reports
  // zero breaches, and zero is not evidence of anything.
  return source === THRESHOLD_SOURCE_GRAPH ? "clear" : "unavailable";
}
