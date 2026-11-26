// How a ranked list grows a page at a time. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { NO_TAIL, hasMore, withPage, type Tail } from "../src/lib/paging.ts";

const id = (s: string) => s;

test("pages are added in order and the next offset counts every row received", () => {
  const first = ["a", "b"];
  const one = withPage(first, NO_TAIL, ["c", "d"], id);
  assert.deepEqual(one, { items: ["c", "d"], fetched: 2, ended: false });
  assert.equal(hasMore(first.length, one, 6), true);
  const two = withPage(first, one, ["e", "f"], id);
  assert.deepEqual(two.items, ["c", "d", "e", "f"]);
  assert.equal(hasMore(first.length, two, 6), false);
});

test("a place that moved across a page boundary is not shown twice", () => {
  // The ranking was rebuilt between two requests: "b" slid down a page, and
  // "c" comes back twice in one page.
  const tail = withPage(["a", "b"], NO_TAIL, ["b", "c", "c", "d"], id);
  assert.deepEqual(tail.items, ["c", "d"]);
  // The offset still moves by what the server sent, or the same page would be asked for again.
  assert.equal(tail.fetched, 4);
});

test("an empty page ends the list whatever the total said", () => {
  const tail: Tail<string> = withPage(["a"], NO_TAIL, [], id);
  assert.equal(tail.ended, true);
  assert.equal(hasMore(1, tail, 100), false);
});

test("an empty or complete first page has nothing after it", () => {
  assert.equal(hasMore(0, NO_TAIL, 0), false);
  assert.equal(hasMore(50, NO_TAIL, 50), false);
  assert.equal(hasMore(50, NO_TAIL, 51), true);
});
