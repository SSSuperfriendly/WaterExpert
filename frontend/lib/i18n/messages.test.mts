/**
 * Both locales have to carry the same keys.
 *
 * `messages.ts` types each tree as `MessageTree`, which catches a *typo* in a
 * key at the point of use but not an omission: `t("agent.predictedTurbidity")`
 * with the key present only in `zh-CN` compiles, ships, and renders the
 * literal string `agent.predictedTurbidity` to whichever reader is on the
 * other locale. Nothing else in the build looks at both trees at once, so a
 * key added to one and forgotten in the other is invisible until an
 * English-speaking operator sees a dotted path where a label should be.
 *
 * A missing key and an extra key are the same defect from either side, so both
 * directions are asserted, and the failure message names the paths rather than
 * just the counts.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { messages } from "./messages.ts";

type Tree = { [key: string]: string | Tree };

/** Every leaf path, in a stable order, so failures are comparable. */
function leaves(tree: Tree, prefix = ""): string[] {
  const out: string[] = [];
  for (const key of Object.keys(tree).sort()) {
    const value = tree[key];
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out.push(path);
    else out.push(...leaves(value, path));
  }
  return out;
}

const zh = leaves(messages["zh-CN"] as Tree);
const en = leaves(messages["en-US"] as Tree);

test("the two locales define exactly the same keys", () => {
  const zhOnly = zh.filter((key) => !en.includes(key));
  const enOnly = en.filter((key) => !zh.includes(key));

  assert.deepEqual(zhOnly, [], `missing from en-US: ${zhOnly.join(", ")}`);
  assert.deepEqual(enOnly, [], `missing from zh-CN: ${enOnly.join(", ")}`);
});

/** The value at `path`, or `undefined` if the path does not resolve. */
function at(tree: Tree, path: string): string | Tree | undefined {
  let node: string | Tree | undefined = tree;
  for (const key of path.split(".")) {
    if (typeof node !== "object") return undefined;
    node = node[key];
  }
  return node;
}

test("no leaf is an empty string", () => {
  // An empty label renders as blank, which reads as a layout bug rather than
  // as a translation that has not been written yet.
  const empty = (["zh-CN", "en-US"] as const).flatMap((locale) =>
    leaves(messages[locale] as Tree)
      .filter((path) => at(messages[locale] as Tree, path) === "")
      .map((path) => `${locale}:${path}`)
  );
  assert.deepEqual(empty, []);
});
