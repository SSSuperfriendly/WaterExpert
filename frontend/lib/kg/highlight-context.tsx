"use client";

import * as React from "react";

import type { KgHighlight } from "@/lib/kg/vis-network";

/**
 * The subgraph currently highlighted on the canvas, shared across tabs.
 *
 * A context rather than lifted state in the page, for one concrete reason: the
 * tabs unmount their inactive panels (Base UI's `Tabs.Panel` defaults to
 * `keepMounted={false}`), so the QA panel that sets a highlight and the view
 * panel that draws it are never mounted at the same time. Whoever mounts later
 * has to be able to read what the other one wrote.
 *
 * The default value is `null`, which is what makes this optional: a view panel
 * rendered outside a provider behaves exactly as it did before highlighting
 * existed.
 */
export interface KgHighlightValue {
  highlight: KgHighlight | null;
  setHighlight: (highlight: KgHighlight | null) => void;
}

const KgHighlightContext = React.createContext<KgHighlightValue | null>(null);

export function KgHighlightProvider({ children }: { children: React.ReactNode }) {
  const [highlight, setHighlight] = React.useState<KgHighlight | null>(null);
  const value = React.useMemo(() => ({ highlight, setHighlight }), [highlight]);
  return <KgHighlightContext.Provider value={value}>{children}</KgHighlightContext.Provider>;
}

/** Returns `null` outside a provider — callers must handle that. */
export function useKgHighlight(): KgHighlightValue | null {
  return React.useContext(KgHighlightContext);
}
