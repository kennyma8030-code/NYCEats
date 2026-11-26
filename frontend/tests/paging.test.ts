// How a ranked list grows a page at a time. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { NO_TAIL, hasMore, withPage, type Tail } from "../src/lib/paging.ts";

const id = (s: string) => s;
const SIZE = 2;

test("pages are added in order and a short page ends the list", () => {
  const first = ["a", "b"];
  const one = withPage(first, NO_TAIL, ["c", "d"], id, 5, SIZE);
  assert.deepEqual(one, { items: ["c", "d"], fetched: 2, ended: false, total: 5 });
  assert.equal(hasMore(first.length, one, SIZE), true);
  const two = withPage(first, one, ["e"], id, 5, SIZE);
  assert.deepEqual(two.items, ["c", "d", "e"]);
  assert.equal(hasMore(first.length, two, SIZE), false);
});

test("a place that moved across a page boundary is not shown twice", () => {
  // The ranking was rebuilt between two requests: "b" slid down a page, and
  // "c" comes back twice in one page.
  const tail = withPage(["a", "b"], NO_TAIL, ["b", "c", "c", "d"], id, 9, 4);
  assert.deepEqual(tail.items, ["c", "d"]);
  // The offset still moves by what the server sent, or the same page would be asked for again.
  assert.equal(tail.fetched, 4);
  // Two rows were dropped, but the page came back full: the list goes on.
  assert.equal(tail.ended, false);
});

test("reaching the first total does not end a list that has grown", () => {
  // The first page said 4; the list is longer by the time its second page is read.
  const tail = withPage(["a", "b"], NO_TAIL, ["c", "d"], id, 6, SIZE);
  assert.equal(hasMore(2, tail, SIZE), true);
  assert.equal(tail.total, 6);
});

test("an empty page ends the list and keeps the last count it was given", () => {
  const one = withPage(["a", "b"], NO_TAIL, ["c", "d"], id, 4, SIZE);
  const tail: Tail<string> = withPage(["a", "b"], one, [], id, 0, SIZE);
  assert.equal(tail.ended, true);
  assert.equal(tail.total, 4);
  assert.equal(hasMore(2, tail, SIZE), false);
});

test("a short first page has nothing after it, a full one may", () => {
  assert.equal(hasMore(0, NO_TAIL, SIZE), false);
  assert.equal(hasMore(1, NO_TAIL, SIZE), false);
  assert.equal(hasMore(2, NO_TAIL, SIZE), true);
});
