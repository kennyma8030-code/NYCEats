// What a search result says its count is, and how the rest of its comments
// are paged. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Mention, SearchItem } from "../src/api/types";
import {
  NOTHING_LOADED, afterIds, afterPage, commentTotal, countedBy, loadedStore, moreLabel, nextComments, nextRequest,
  resultId, seenCount,
} from "../src/lib/results.ts";

const item = (ids: number[] | null, loaded: number[]): SearchItem => ({
  entity_key: "k", name: "K", cuisine: null, borough: null, neighborhood: null,
  people: 14, total_people: 40, best_similarity: null, mention_ids: ids,
  comments: loaded.map((mention_id) => ({ mention_id }) as SearchItem["comments"][number]),
});

test("a list says what its count counts", () => {
  assert.equal(countedBy({ semantic: "ok", ranked_by: "matching_people" }), "wrote a matching comment");
  assert.equal(countedBy({ semantic: "text", ranked_by: "matching_people" }), "used these words about them");
  assert.equal(countedBy({ semantic: "none", ranked_by: "people" }), "brought them up");
  assert.equal(countedBy({ semantic: "unavailable", ranked_by: "people" }), "brought them up");
});

test("the count opens in full: the button names every comment counted", () => {
  const it = item([5, 4, 3, 2, 1, 9, 8], [5, 4, 3]);
  assert.equal(commentTotal(it), 7);
  assert.equal(moreLabel(it, 3), "Show all 7 comments");
  assert.deepEqual(nextComments(it, [5, 4, 3]), [2, 1, 9, 8]);
  assert.equal(moreLabel(it, 7), null);
  assert.deepEqual(nextComments(it, [5, 4, 3, 2, 1, 9, 8]), []);
});

test("a long list of comments is read a page at a time, in the result's order", () => {
  const ids = Array.from({ length: 120 }, (_, i) => 1000 - i);
  const it = item(ids, ids.slice(0, 3));
  assert.equal(moreLabel(it, 3), "Show 50 more of 120 comments");
  const first = nextComments(it, ids.slice(0, 3));
  assert.deepEqual(first, ids.slice(3, 53));
  assert.equal(moreLabel(it, 53), "Show 50 more of 120 comments");
  assert.equal(moreLabel(it, 103), "Show all 120 comments");
  assert.deepEqual(nextComments(it, ids.slice(0, 103)), ids.slice(103));
});

test("a comment that did not come back is not asked for forever", () => {
  // The answer was short one comment (gone since the search): what is left
  // to ask for is only what was never shown.
  const it = item([1, 2, 3, 4], [1, 2, 3]);
  assert.deepEqual(nextComments(it, [1, 2, 3]), [4]);
});

test("the board's own count names no comments: the place's page opens them", () => {
  const it = item(null, [1, 2, 3]);
  assert.equal(commentTotal(it), 3);
  assert.equal(moreLabel(it, 3), null);
  assert.deepEqual(nextComments(it, [1, 2, 3]), []);
  assert.equal(nextRequest(it, NOTHING_LOADED, true), null);
});

const rows = (ids: number[]) => ids.map((mention_id) => ({ mention_id }) as Mention);

test("a text match counts more comments than it names, and the rest are read by position", () => {
  // 130 comments counted, 4 named, 3 shown.
  const it = { ...item([1, 2, 3, 4], [1, 2, 3]), comment_count: 130 };
  assert.equal(commentTotal(it), 130);
  assert.equal(moreLabel(it, 3), "Show 50 more of 130 comments");
  // The named ids first.
  assert.deepEqual(nextRequest(it, NOTHING_LOADED, true), { ids: [4] });
  let l = afterIds(NOTHING_LOADED, [4], rows([4]));
  assert.equal(seenCount(it, l), 4);
  // Then by position, from where the names ended.
  assert.deepEqual(nextRequest(it, l, true), { offset: 4, limit: 50 });
  l = afterPage(it, l, 50, rows(Array.from({ length: 50 }, (_, i) => 100 + i)));
  assert.deepEqual(nextRequest(it, l, true), { offset: 54, limit: 50 });
  assert.equal(moreLabel(it, seenCount(it, l)), "Show 50 more of 130 comments");
  l = afterPage(it, l, 50, rows(Array.from({ length: 50 }, (_, i) => 200 + i)));
  // The last page asks only for what is left.
  assert.deepEqual(nextRequest(it, l, true), { offset: 104, limit: 26 });
  assert.equal(moreLabel(it, seenCount(it, l)), "Show all 130 comments");
  l = afterPage(it, l, 26, rows(Array.from({ length: 26 }, (_, i) => 300 + i)));
  assert.equal(nextRequest(it, l, true), null);
  assert.equal(moreLabel(it, seenCount(it, l)), null);
  assert.equal(l.extra.length, 127);
  // An answer that does not say what it matched cannot be paged.
  assert.equal(nextRequest(it, afterIds(NOTHING_LOADED, [4], rows([4])), false), null);
});

test("a page that comes back short, or repeats a comment, ends the asking", () => {
  const it = { ...item([1, 2], [1, 2]), comment_count: 60 };
  // A comment already on screen is not shown twice, and still counts as read.
  let l = afterPage(it, NOTHING_LOADED, 50, rows([2, ...Array.from({ length: 49 }, (_, i) => 100 + i)]));
  assert.equal(l.extra.length, 49);
  assert.equal(seenCount(it, l), 52);
  assert.deepEqual(nextRequest(it, l, true), { offset: 52, limit: 8 });
  // Three came where eight were asked for: the rest are gone since the search.
  l = afterPage(it, l, 8, rows([900, 901, 902]));
  assert.equal(nextRequest(it, l, true), null);
  assert.equal(moreLabel(it, seenCount(it, l)), null);
  // Ids that did not come back are written off the same way.
  const named = item([1, 2, 3, 4], [1, 2]);
  const after = afterIds(NOTHING_LOADED, [3, 4], rows([3]));
  assert.deepEqual(after.missing, [4]);
  assert.equal(nextRequest(named, after, false), null);
});

test("comments read for a result outlive the list that drew them, for that answer only", () => {
  const kept = loadedStore();
  const it = item([1, 2, 3, 4], [1, 2, 3]);
  const l = afterIds(NOTHING_LOADED, [4], rows([4]));
  assert.equal(kept.get("nyc|pizza|fast", resultId(it)), NOTHING_LOADED);
  kept.set("nyc|pizza|fast", resultId(it), l);
  // The list was taken down and drawn again: nothing is asked for twice.
  assert.equal(kept.get("nyc|pizza|fast", resultId(it)), l);
  assert.equal(nextRequest(it, kept.get("nyc|pizza|fast", resultId(it)), false), null);
  // Not another reading of the query, nor the same place counted differently.
  assert.equal(kept.get("nyc|pizza|full", resultId(it)), NOTHING_LOADED);
  assert.equal(kept.get("nyc|pizza|fast", resultId(item([1, 2, 3, 4, 5], [1, 2, 3]))), NOTHING_LOADED);
  // One answer at a time: a new search forgets the last one's.
  kept.set("nyc|tacos|fast", "x", l);
  assert.equal(kept.get("nyc|pizza|fast", resultId(it)), NOTHING_LOADED);
});
