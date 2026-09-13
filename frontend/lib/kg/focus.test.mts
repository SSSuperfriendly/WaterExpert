/**
 * Node's built-in runner with native TypeScript type-stripping.
 *
 * The frontend has no test framework: `package.json` lists dev/build/start/lint
 * and nothing else, and adding vitest or jest to test two pure functions would
 * mean a dependency tree, a config file and a runner to keep current. Node 26
 * strips the types itself, so `node --test` runs these files directly.
 *
 * The trade-off is real and worth stating: this only works for modules that use
 * *erasable* TypeScript — types, interfaces, `as`, annotations. `enum`, a
 * parameter property, or a namespace would need a transform and would fail
 * here. That is a constraint on what can live in `focus.ts`, not a limitation
 * of the tests.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { fitTarget, focusIds, requestKey } from "./focus.ts";

const held = (...ids: string[]) => ({ has: (id: string) => ids.includes(id) });

test("an id the canvas does not hold is dropped", () => {
  assert.deepEqual(focusIds(["platform::浊度"], held("inherited::TURBIDITY")), []);
});

test("only the ids the canvas holds survive, in the order asked", () => {
  const canvas = held("platform::浊度", "platform::风");
  assert.deepEqual(
    focusIds(["platform::风", "inherited::SEDIMENT", "platform::浊度"], canvas),
    ["platform::风", "platform::浊度"]
  );
});

test("an empty request focuses nothing", () => {
  assert.deepEqual(focusIds([], held("platform::风")), []);
});

test("an empty intersection asks for no fit", () => {
  // The crash, stated as a unit: an answer from the inherited graph against a
  // canvas of platform nodes intersects to nothing, and nothing is what must
  // reach network.fit.
  assert.equal(fitTarget(focusIds(["inherited::SEDIMENT"], held("platform::风"))), null);
});

test("a non-empty intersection is passed through as a copy", () => {
  const ids = ["platform::风"];
  const target = fitTarget(ids);
  assert.deepEqual(target, ids);
  assert.notEqual(target, ids);
});

test("an empty list is never passed to fit", () => {
  // vis-network substitutes every node for an empty list, so this would zoom
  // out to the whole graph rather than frame anything.
  assert.equal(fitTarget([]), null);
});

const node = (name: string) => ({ source_id: "inherited", name });

test("focusing a different entity is not a different request", () => {
  // The regression this key's shape exists to prevent: `focusNode` is the one
  // field the backend never sees, so clicking an entity to locate it must not
  // refetch the same subgraph and relayout the canvas to show an identical
  // picture.
  const base = { nodes: [node("TURBIDITY"), node("SEDIMENT")] };
  assert.equal(
    requestKey({ ...base, focusNode: node("TURBIDITY") }),
    requestKey({ ...base, focusNode: node("SEDIMENT") })
  );
  assert.equal(requestKey({ ...base }), requestKey({ ...base, focusNode: node("SEDIMENT") }));
});

test("focusing a different edge is a different request", () => {
  // The opposite case: `focus` *is* sent, because the backend is what decides
  // which parallel edge that citation points at.
  const base = { nodes: [node("TURBIDITY")] };
  const edge = { source_id: "inherited", source: "TURBIDITY", target: "SEDIMENT" };
  assert.notEqual(
    requestKey({ ...base, focus: { ...edge, index: 0 } }),
    requestKey({ ...base, focus: { ...edge, index: 1 } })
  );
});

test("a request is unchanged by the order it was assembled in", () => {
  const a = node("TURBIDITY");
  const b = node("SEDIMENT");
  assert.equal(
    requestKey({ nodes: [a, b], communityIds: ["inherited:c0001", "platform:c0004"] }),
    requestKey({ nodes: [b, a], communityIds: ["platform:c0004", "inherited:c0001"] })
  );
});

test("adding a community or a neighbour hop is a different request", () => {
  const base = { nodes: [node("TURBIDITY")] };
  assert.notEqual(requestKey(base), requestKey({ ...base, communityIds: ["inherited:c0001"] }));
  assert.notEqual(requestKey(base), requestKey({ ...base, includeNeighbours: true }));
});
