"use client";

import * as React from "react";
import { useAppStore } from "@/lib/stores/app-store";
import type { ArtifactScope } from "@/lib/api/endpoints";

/**
 * Resolve the scope a result endpoint should read.
 *
 * Review item 5: the backend no longer falls back to the shared research
 * artifacts, so a result read must name *something*. The precedence here is
 *
 *   1. the active case (the normal evidence-chain path),
 *   2. the active job (a run not yet bound to a case),
 *   3. ``scope=integrated`` (the explicitly-labelled shared artifacts).
 *
 * The returned object is memoized against its two primitives so passing it as a
 * dependency to ``useApi`` only refetches when the case or job actually changes.
 *
 * Pages that are genuinely operational — the overview dashboard, which reports
 * the *platform* rather than a specific conclusion — should call
 * :func:`integratedScope` instead and not adopt the active case.
 */
export function useArtifactScope(): ArtifactScope {
  const activeCaseId = useAppStore((s) => s.activeCaseId);
  const activeJobId = useAppStore((s) => s.activeJobId);

  return React.useMemo<ArtifactScope>(() => {
    if (activeCaseId) {
      return { case_id: activeCaseId, job_id: activeJobId ?? undefined };
    }
    if (activeJobId) {
      return { job_id: activeJobId };
    }
    return { scope: "integrated" };
  }, [activeCaseId, activeJobId]);
}

/** The shared research artifacts, explicitly labelled for the overview shell. */
export function integratedScope(): ArtifactScope {
  return { scope: "integrated" };
}
