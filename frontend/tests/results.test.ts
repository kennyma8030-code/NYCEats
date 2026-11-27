// What a search result says its count is, and how the rest of its comments
// are paged. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { SearchItem } from "../src/api/types";
import { commentTotal, countedBy, moreLabel, nextComments } from "../src/lib/results.ts";

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
});
