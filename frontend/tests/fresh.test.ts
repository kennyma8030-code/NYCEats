// The rules for what fetched data may be shown, without a browser.
// Run with `npm test` (node's own runner; Node 22.6+ strips the types).
import assert from "node:assert/strict";
import { test } from "node:test";
import { fetchView, type FetchInner } from "../src/lib/fresh.ts";

test("a repeated need is one filter, as the API reads it", async () => {
  const { filtersFromQuery } = await import("../src/state/filters.ts");
  const f = filtersFromQuery("?need=value&need=value&flaw=food&flaw=food", null);
  assert.deepEqual(f.needs, ["value"]);
  assert.deepEqual(f.flaws, ["food"]);
});

test("fetchView labels data with the key it was loaded for", () => {
  const settled: FetchInner<string> = { key: "a", data: "A", dataKey: "a", error: null, loading: false };
  assert.deepEqual(fetchView(settled, "a"), { data: "A", dataKey: "a", current: true, error: null, loading: false });

  // The render after the key changed, before the effect has run.
  const v = fetchView(settled, "b");
  assert.equal(v.current, false);
  assert.equal(v.loading, true);

  // An error is reported for its own key only, and leaves no data behind.
  const failed: FetchInner<string> = { key: "b", data: null, dataKey: null, error: "500", loading: false };
  assert.deepEqual(fetchView(failed, "b"), { data: null, dataKey: null, current: false, error: "500", loading: false });
  assert.equal(fetchView(failed, "c").error, null);
  assert.equal(fetchView(failed, "c").loading, true);

  assert.equal(fetchView(settled, null).loading, false);
});
