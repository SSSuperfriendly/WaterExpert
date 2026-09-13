/**
 * The empty breach list, which means two opposite things.
 *
 * CMFBE falls back rather than failing a request, and since the thresholds now
 * arrive with the request rather than living in the agent's source, "no levels
 * were supplied" is a state that really occurs — a direct call to the agent, or
 * a platform whose threshold graph is missing. A run in that state reports zero
 * breaches for the same reason a clean run does. Only one of them may be shown
 * as a clean bill of health.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { thresholdVerdict } from "./thresholds.ts";

test("levels that were screened and not exceeded read as clear", () => {
  assert.equal(thresholdVerdict("knowledge_graph", 0), "clear");
});

test("levels that were screened and exceeded read as breached", () => {
  assert.equal(thresholdVerdict("knowledge_graph", 2), "breached");
});

test("no levels supplied is not an all-clear, even with no breaches", () => {
  // The whole point. A run handed no thresholds reports zero breaches, and zero
  // breaches from a screening that never happened is not a result.
  assert.equal(thresholdVerdict("unavailable", 0), "unavailable");
});

test("a source this build does not know is treated as no screening", () => {
  // Optimistic here would mean a future agent's new source string renders as
  // "clear" on the strength of a word this version cannot interpret.
  assert.equal(thresholdVerdict("some_future_source", 0), "unavailable");
  assert.equal(thresholdVerdict(undefined, 0), "unavailable");
  assert.equal(thresholdVerdict("", 0), "unavailable");
});

test("breaches from an unknown source are still reported as breaches", () => {
  // The other direction: a report of an exceeded level has to be shown whatever
  // the source is called. Suppressing it would be the unsafe reading.
  assert.equal(thresholdVerdict("some_future_source", 3), "breached");
});
