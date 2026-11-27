// What the search box suggests from the vocabulary. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { fold, matchTerms, termCount } from "../src/lib/terms.ts";

const vocab = {
  cuisines: [["Italian", 412], ["Indian", 180], ["Pizza", 300]] as [string, number][],
  areas: [["Brooklyn", 900], ["west village", 240], ["Little Italy", 40]] as [string, number][],
  dishes: [["pizza", 5000], ["soup dumplings", 800], ["italian beef", 30]] as [string, number][],
  tags: [["date night", 700], ["soup dumplings", 12], ["cash only", 300]] as [string, number][],
};

const labels = (q: string, limit?: number) => matchTerms(vocab, q, limit).map((h) => `${h.kind}:${h.label}`);

test("folding meets what people type", () => {
  assert.equal(fold("  Café  Katz’s! "), "cafe katzs");
});

test("one letter suggests nothing", () => {
  assert.deepEqual(labels("i"), []);
  assert.deepEqual(labels("  "), []);
});

test("a prefix finds filters before things matched by meaning", () => {
  assert.deepEqual(labels("ital"), ["cuisine:Italian", "dish:italian beef", "area:Little Italy"]);
  assert.deepEqual(labels("in"), ["cuisine:Indian"]);
});

test("the whole label beats a longer one starting with it", () => {
  assert.deepEqual(labels("pizza"), ["cuisine:Pizza"]);
  assert.deepEqual(labels("west village"), ["area:west village"]);
});

test("a later word matches, and a dish that is also a tag is listed once", () => {
  assert.deepEqual(labels("dump"), ["dish:soup dumplings"]);
  assert.deepEqual(labels("night"), ["tag:date night"]);
});

test("the limit keeps the best", () => {
  assert.deepEqual(labels("ital", 1), ["cuisine:Italian"]);
});

test("counts say what they count", () => {
  assert.equal(termCount({ kind: "cuisine", label: "Italian", n: 1 }), "1 place");
  assert.equal(termCount({ kind: "dish", label: "pizza", n: 5000 }), `${(5000).toLocaleString()} mentions`);
});
