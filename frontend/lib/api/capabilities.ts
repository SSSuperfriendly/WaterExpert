"use client";

import { endpoints } from "./endpoints";
import type { Capabilities } from "./contracts";

/**
 * One shared capabilities fetch for the whole app.
 *
 * The header, upload form, job runner and event form all need the same
 * vocabulary, so the promise is memoized at module scope: the first component to
 * ask starts the request and every other one awaits it instead of issuing a
 * second call.
 */
let cache: Promise<Capabilities> | null = null;

export function getCapabilities(): Promise<Capabilities> {
  if (!cache) {
    cache = endpoints.capabilities();
  }
  return cache;
}

/** Drop the memoized response (used after a capability-affecting change). */
export function resetCapabilities(): void {
  cache = null;
}
