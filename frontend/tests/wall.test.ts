// What goes on the landing page's wall, what a row and a card say, and
// where the map frames a list. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { FeedItem, LedgerItem, Rating } from "../src/api/types.ts";
import { cityView, pinBounds } from "../src/lib/cities.ts";
import { cardStat, rowMetric, sortNote } from "../src/lib/sorts.ts";
import { quoteLine, wallColumns, wallPlaces, wallPool, wallQuotes, type WallCard } from "../src/lib/wall.ts";

const rating = { pos: 53, neg: 0, pct_pos: 1, rankable: true } as Rating;
const item = (over: Partial<LedgerItem>) => ({ entity_key: "raku", name: "Raku", current: 12, previous: 1, rating, ...over }) as LedgerItem;

const comment = (over: Partial<FeedItem>): FeedItem => ({
  kind: "comment", id: "t1_a", cursor: "c", author: "a", score: 1, created_utc: "2026-11-01T00:00:00Z",
  body: "Best pastrami I have ever had, worth the line.", permalink: "/r/FoodNYC/x", was_deleted_later: false,
  title: null, num_comments: null, places: [{ key: "katzs", name: "Katz's" }], ...over,
});

test("a row shows the one number its list is ranked by", () => {
  assert.deepEqual(rowMetric("loved", item({})), { big: "100%", small: "53 people" });
  assert.deepEqual(rowMetric("talked", item({})), { big: "12", small: "mentions" });
  assert.deepEqual(rowMetric("trending", item({})), { big: "+11", small: "12 vs 1 mention" });
  assert.deepEqual(rowMetric("gems", item({ rating: null })), { big: "–", small: "" });
});

test("a card says the same number as a phrase", () => {
  assert.equal(cardStat("loved", item({}), 365), "100% positive, 53 people");
  assert.equal(cardStat("talked", item({ current: 1516 }), 365), "1,516 mentions");
  assert.equal(cardStat("trending", item({}), 7), "+11 mentions this week");
  assert.equal(cardStat("loved", item({ rating: null }), 365), "");
});

test("the note under the sort names the period it counts", () => {
  assert.equal(sortNote("talked", 365, null), "Most mentions over the last 12 months.");
  assert.equal(sortNote("trending", 7, null), "Talked about more this week than the week before.");
  assert.equal(sortNote("trending", 30, null), "Talked about more in the last month than the month before.");
});

test("only a comment that reads as one line becomes a card", () => {
  assert.equal(quoteLine("  Get the udon.\n\nTrust me on this one.  "), "Get the udon. Trust me on this one.");
  assert.equal(quoteLine("ok"), null);
  assert.equal(quoteLine("see https://example.com/menu for the full list of dishes"), null);
  const long = `${"The noodles were springy and the broth was deep. ".repeat(2)}${"x".repeat(200)}.`;
  assert.equal(quoteLine(long), "The noodles were springy and the broth was deep. The noodles were springy and the broth was deep.");
  assert.equal(quoteLine("x".repeat(300)), null);
});

test("the wall leaves out deleted comments, posts and comments about no place", () => {
  const cards = wallQuotes([
    comment({ id: "1", score: 2 }),
    comment({ id: "2", body: "Honestly overhyped, the bread falls apart.", score: 9 }),
    comment({ id: "3", body: "This one was deleted after we read it.", was_deleted_later: true }),
    comment({ id: "4", body: "A post, which names no restaurant at all.", kind: "post" }),
    comment({ id: "5", body: "A comment that mentions nowhere in particular.", places: [] }),
  ], "FoodNYC");
  assert.deepEqual(cards.map((c) => c.text), [
    "Honestly overhyped, the bread falls apart.", "Best pastrami I have ever had, worth the line.",
  ]);
  assert.equal(cards[0].kind === "quote" && cards[0].sub, "r/FoodNYC on Katz's");
});

test("comments and places alternate, and the rankings take turns", () => {
  const q = (text: string): WallCard => ({ kind: "quote", text, sub: "" });
  const loved = wallPlaces("loved", [item({}), item({ name: "Jua" })]);
  const talked = wallPlaces("talked", [item({ name: "Katz's" })]);
  const pool = wallPool([q("a"), q("b"), q("c"), q("d")], [loved, talked]);
  assert.deepEqual(pool.map((c) => c.text), ["a", "Raku", "b", "Katz's", "c", "Jua", "d"]);
  assert.equal(loved[0].kind === "place" && loved[0].label, "Most loved");
});

test("columns loop without a jump and do not move in step", () => {
  const pool = Array.from({ length: 20 }, (_, i): WallCard => ({ kind: "quote", text: String(i), sub: "" }));
  const cols = wallColumns(pool, 4, 7, 95, 11);
  assert.equal(cols.length, 4);
  for (const c of cols) {
    assert.equal(c.cards.length, 14);
    assert.deepEqual(c.cards.slice(0, 7), c.cards.slice(7));
    assert.ok(c.delay <= 0 && -c.delay < c.duration);
  }
  assert.notEqual(cols[0].cards[0], cols[1].cards[0]);
  assert.equal(new Set(cols.map((c) => c.duration)).size, 4);
  assert.deepEqual(wallColumns([], 4, 7, 95, 11), []);
});

test("the map frames the body of a list, not its outliers", () => {
  assert.equal(pinBounds([]), null);
  assert.equal(pinBounds([{ lat: 40.7, lng: -74 }]), null);
  assert.deepEqual(pinBounds([{ lat: 40.7, lng: -74 }, { lat: 40.8, lng: -73.9 }]), [[-74, 40.7], [-73.9, 40.8]]);
  // Twenty pins in Manhattan and one far south-west: the far one is left out of the frame.
  const many = Array.from({ length: 20 }, (_, i) => ({ lat: 40.7 + i * 0.005, lng: -74 + i * 0.002 }));
  const [[west, south]] = pinBounds([...many, { lat: 40.5, lng: -74.25 }])!;
  assert.ok(south >= 40.7 && west >= -74);
});

test("an unknown city opens on the continent, not on another city", () => {
  assert.deepEqual(cityView("FoodNYC").center, [-73.972, 40.737]);
  assert.ok(cityView("somewhere").zoom < 5);
});
