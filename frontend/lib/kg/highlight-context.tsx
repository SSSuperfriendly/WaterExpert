"use client";

import * as React from "react";

/**
 * The subgraph the canvas should draw, and which part of it a citation points
 * at, shared across tabs.
 *
 * A context rather than lifted state in the page, for one concrete reason: the
 * tabs unmount their inactive panels (Base UI's `Tabs.Panel` defaults to
 * `keepMounted={false}`), so the QA panel that sets a request and the view
 * panel that draws it are never mounted at the same time. Whoever mounts later
 * has to be able to read what the other one wrote.
 *
 * What travels is a *request*, not a list of ids. That is the whole correction:
 * the QA panel used to send the ids it retrieved and the canvas intersected them
 * with a graph built from a different source, which came out empty and then
 * threw. Asking the backend for the subgraph means the panel never has to know
 * what the canvas holds — and a request for a community, a neighbour expansion
 * or a single focused edge rides the same path as the initial one, so there is
 * one mechanism instead of three.
 *
 * The default value is `null`, which is what makes this optional: a view panel
 * rendered outside a provider behaves exactly as it did before any of this
 * existed.
 */

/** One entity to draw, named the way the API names it. */
export interface KgNodeRef {
  source_id: string;
  name: string;
}

/** The single edge a citation points at, disambiguated among parallel edges. */
export interface KgEdgeFocus {
  source_id: string;
  source: string;
  target: string;
  index?: number;
}

export interface KgSubgraphRequest {
  /** The entities the answer cited — kept whatever the caps say. */
  nodes: KgNodeRef[];
  /** Communities to pull in, by id. */
  communityIds?: string[];
  /** Whether to add one hop of surroundings. */
  includeNeighbours?: boolean;
  /** The edge to single out once drawn, if any. */
  focus?: KgEdgeFocus;
  /**
   * The entity to single out once drawn.
   *
   * Client-side only: the backend is not told about it, because it changes
   * nothing about what to draw — ``nodes`` already carries the entity, and the
   * subgraph is the answer's own. Its whole job is to tell the canvas which of
   * the drawn things the reader asked to see. Without it, "locate this entity"
   * would have no way to say *which* entity, since everything drawn is already
   * lit.
   */
  focusNode?: KgNodeRef;
}

export interface KgHighlight {
  /** What this shows, for the panel that asked for it. */
  title: string;
  request: KgSubgraphRequest;
}

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
