/**
 * The pure decisions the canvas makes about a highlight.
 *
 * Extracted from the vis-network binding because they are the parts that were
 * wrong, and because a decision that only exists inside a rendered canvas can
 * only be tested by rendering one — which this project cannot do. Nothing here
 * touches the DOM or vis-network: it takes ids in and returns ids out.
 */

import type { KgSubgraphRequest } from "./highlight-context";

/** A node or edge id as the canvas knows it. */
export type IdSet = { has: (id: string) => boolean };

/**
 * The ids in `wanted` that the canvas actually holds, in `wanted`'s order.
 *
 * This exists because `network.fit` is not tolerant of strangers. Handed a node
 * id that is not in the graph it reaches `getRange`, indexes into an undefined
 * entry and throws `TypeError: Cannot read properties of undefined (reading
 * 'shape')` — from inside a React effect, with no error boundary above it, which
 * renders as the blank "This page couldn't load" page.
 *
 * Intersecting first is not defensive coding around a rare case: the two graphs
 * are addressed by different vocabularies, so an answer grounded in one used to
 * ask the canvas to focus entities from the other every single time.
 */
export function focusIds(wanted: readonly string[], available: IdSet): string[] {
  return wanted.filter((id) => available.has(id));
}

/**
 * Whether to call `fit` at all, and with what.
 *
 * Returns `null` for "do not call it". An empty array is not the safe choice:
 * vis-network's node-list normaliser substitutes *every* node when the list is
 * empty, so `fit({ nodes: [] })` zooms out to the whole graph — the opposite of
 * focusing, and it would silently undo the highlight it was meant to frame.
 */
export function fitTarget(ids: readonly string[]): string[] | null {
  return ids.length > 0 ? [...ids] : null;
}

/**
 * A stable key for a request, so the panel can tell "the same subgraph" from "a
 * different one" without comparing object identity — every render builds a
 * fresh request object, and refetching on identity would loop forever.
 *
 * The key answers exactly one question: *would the backend return something
 * else?* Everything the backend is told is in here, and nothing else is. That
 * is why `focusNode` is deliberately absent. It is the one field of a request
 * the API never sees — it only tells the canvas which of the already-drawn
 * things the reader asked to see — so a new `focusNode` draws the same subgraph
 * and must not be allowed to look like a new one. When it was in the key,
 * clicking an entity to locate it refetched a byte-identical payload and
 * rebuilt the whole canvas, restabilising the layout to arrive at a picture
 * that had not changed.
 *
 * The effect that *does* have to notice a newly focused entity depends on the
 * highlight object itself, not on this string — so nothing is lost by leaving
 * it out here.
 *
 * Order is not identity: the same entities and communities in a different order
 * are the same request.
 */
export function requestKey(request: KgSubgraphRequest): string {
  const focus = request.focus;
  return JSON.stringify({
    nodes: [...request.nodes]
      .map((node) => `${node.source_id}::${node.name}`)
      .sort(),
    communityIds: [...(request.communityIds ?? [])].sort(),
    includeNeighbours: Boolean(request.includeNeighbours),
    focus: focus ? [focus.source_id, focus.source, focus.target, focus.index ?? 0] : null,
  });
}
