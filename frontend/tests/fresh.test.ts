// The rules for what fetched data may be shown, without a browser.
// Run with `npm test` (node's own runner; Node 22.6+ strips the types).
import assert from "node:assert/strict";
import { test } from "node:test";
import { fetchView, ledgerMatches, visibleLedgerItems, type FetchInner } from "../src/lib/fresh.ts";
import type { LedgerItem, LedgerResponse } from "../src/api/types.ts";
import type { Filters } from "../src/state/filters.ts";

const filters: Filters = {
  algo: "v1", topic: "", category: "trending", window: 7, cuisine: "", borough: "", needs: [], flaws: [],
};

const row = (k: string) => ({ entity_key: k }) as LedgerItem;

function response(f: Filters, keys: string[]): LedgerResponse {
  return {
    category: f.category, window_days: f.window, bucket_days: 1, algo: f.algo,
    topic: f.topic.trim() || null, cuisine: f.cuisine || null, borough: f.borough || null,
    needs: [...f.needs], flaws: [...f.flaws], total: keys.length, items: keys.map(row),
  };
}

test("a response matches only the filters it echoes", () => {
  const f: Filters = { ...filters, topic: " omakase ", cuisine: "Japanese", needs: ["value", "service"] };
  const d = response(f, ["a"]);
  assert.ok(ledgerMatches(d, f));
  assert.ok(ledgerMatches(d, { ...f, needs: ["service", "value"] }), "order of needs does not matter");
  for (const patch of [
    { cuisine: "" }, { borough: "Queens" }, { needs: ["value"] }, { flaws: ["food"] },
    { topic: "ramen" }, { algo: "v2" }, { window: 30 }, { category: "top" },
  ] as Partial<Filters>[]) {
    assert.ok(!ledgerMatches(d, { ...f, ...patch }), JSON.stringify(patch));
  }
});

test("an error never shows the previous filters' rows", () => {
  const old = response(filters, ["a", "b"]);
  const now: Filters = { ...filters, borough: "Brooklyn" };
  assert.deepEqual(visibleLedgerItems(old, now, false, "boom").items, []);
  assert.deepEqual(visibleLedgerItems(old, filters, false, "boom").items, []);
});

test("old rows show only while the new request is in flight", () => {
  const old = response(filters, ["a", "b"]);
  const now: Filters = { ...filters, cuisine: "Pizza" };
  assert.deepEqual(visibleLedgerItems(old, now, true, null), { items: old.items, current: false });
  assert.deepEqual(visibleLedgerItems(old, now, false, null), { items: [], current: false });
  assert.deepEqual(visibleLedgerItems(old, filters, false, null), { items: old.items, current: true });
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
