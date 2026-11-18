// Where a link opens, and what a change of sort, filter or city does to the
// rest of the route. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { applyPatch, formatRoute, HOME_ROUTE, ledgerFilters, parseRoute, type Route } from "../src/state/route.ts";

const nyc: Route = { ...HOME_ROUTE, screen: "city" };

test("a bare link is the landing page, and a city link names its subreddit", () => {
  assert.equal(parseRoute("").screen, "home");
  assert.equal(formatRoute(HOME_ROUTE), "");
  assert.equal(formatRoute(nyc), "?subreddit=FoodNYC");
  assert.deepEqual(parseRoute("?subreddit=FoodNYC"), nyc);
  assert.equal(parseRoute("?subreddit=austinfood").city, "austinfood");
});

test("a route survives the URL", () => {
  const r: Route = {
    ...nyc, city: "FoodLosAngeles", sort: "trending", window: 30, topic: "birria tacos", cuisine: "Mexican",
    borough: "Los Angeles", needs: ["value"], flaws: ["wait"], place: "sonoratown", dev: true,
  };
  assert.deepEqual(parseRoute(formatRoute(r)), r);
});

test("links from the old interface still open New York", () => {
  assert.deepEqual(parseRoute("?r=katzs%20delicatessen"), { ...nyc, place: "katzs delicatessen" });
  assert.equal(parseRoute("?category=top&window=30").sort, "talked");
  assert.equal(parseRoute("?category=top&window=30").window, 30);
  assert.equal(parseRoute("?view=boards&board=gems").sort, "gems");
  // A topic with no sort named lands on a list that can apply it.
  assert.equal(parseRoute("?topic=omakase").sort, "talked");
  assert.equal(parseRoute("?topic=omakase").topic, "omakase");
});

test("a topic or a quality moves a rating board to a list that can filter by it", () => {
  const topic = applyPatch(nyc, { topic: " omakase " });
  assert.equal(topic.sort, "talked");
  assert.equal(topic.topic, "omakase");
  assert.equal(applyPatch(nyc, { needs: ["value"] }).sort, "talked");
  assert.equal(applyPatch({ ...nyc, sort: "trending" }, { flaws: ["wait"] }).sort, "trending");
  // Cuisine and area filter every list, so the sort stays.
  assert.equal(applyPatch(nyc, { cuisine: "Thai" }).sort, "loved");
});

test("choosing a rating board drops the filters it cannot apply", () => {
  const from: Route = { ...nyc, sort: "talked", topic: "omakase", needs: ["value"], cuisine: "Japanese", window: 30 };
  const to = applyPatch(from, { sort: "loved" });
  assert.deepEqual([to.sort, to.topic, to.needs, to.cuisine, to.window], ["loved", "", [], "Japanese", null]);
});

test("an aspect is wanted or complained of, never both", () => {
  const r = applyPatch({ ...nyc, sort: "talked", needs: ["value", "wait"] }, { flaws: ["value"] });
  assert.deepEqual(r.needs, ["wait"]);
  assert.deepEqual(r.flaws, ["value"]);
});

test("another city starts clean, and going home forgets the city", () => {
  const from: Route = { ...nyc, sort: "talked", cuisine: "Thai", place: "raku", dev: true };
  assert.deepEqual(applyPatch(from, { city: "austinfood" }), { ...nyc, city: "austinfood", dev: true });
  assert.deepEqual(applyPatch(from, { screen: "home" }), { ...HOME_ROUTE, dev: true });
  // From the landing page straight onto a place or a topic.
  assert.deepEqual(applyPatch(HOME_ROUTE, { city: "FoodNYC", place: "raku" }), { ...nyc, place: "raku" });
  assert.equal(applyPatch(HOME_ROUTE, { city: "FoodNYC", topic: "ramen" }).sort, "talked");
});

test("the ledger is asked for exactly what the route says", () => {
  const f = ledgerFilters({ ...nyc, sort: "trending", topic: "ramen", borough: "Queens" }, 7);
  assert.deepEqual(f, { algo: "v1", topic: "ramen", category: "trending", window: 7, cuisine: "", borough: "Queens", needs: [], flaws: [] });
  assert.equal(ledgerFilters({ ...nyc, sort: "talked" }, 365).category, "top");
});
