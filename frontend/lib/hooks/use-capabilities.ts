"use client";

import { useApi } from "@/lib/hooks/use-api";
import { getCapabilities } from "@/lib/api/capabilities";

/**
 * The deployment's vocabulary, shared across every selector in the UI. Backed by
 * a module-level cache (see ``lib/api/capabilities``) so many components can
 * call it without many requests.
 */
export function useCapabilities() {
  return useApi(() => getCapabilities());
}
