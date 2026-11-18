// One scroll gesture is one step through the cities, however many wheel
// events it arrives as. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { stepIndex, wheelGestures } from "../src/lib/gesture.ts";

test("a flick and all its coasting is one gesture", () => {
  const g = wheelGestures(200);
  assert.equal(g.fresh(1000), true);
  g.spend();
  // A trackpad keeps sending events for a second or more, never 200ms apart.
  for (let t = 1016; t < 2400; t += 16) assert.equal(g.fresh(t), false, `at ${t}`);
  // Quiet, then a new gesture.
  assert.equal(g.fresh(2700), true);
});

test("a gesture nothing used stays usable until it is spent", () => {
  const g = wheelGestures(200);
  assert.equal(g.fresh(0), true);
  assert.equal(g.fresh(50), true);
  g.spend();
  assert.equal(g.fresh(100), false);
});

test("a gesture that began elsewhere cannot act where it ends up", () => {
  const g = wheelGestures(200);
  // Scrolling down the hero: each event is spent as it passes.
  for (let t = 0; t < 600; t += 20) {
    g.fresh(t);
    g.spend();
  }
  // Still coasting as the cities arrive.
  assert.equal(g.fresh(610), false);
});

test("steps hold at both ends of the list", () => {
  assert.equal(stepIndex(0, 1, 3), 1);
  assert.equal(stepIndex(2, 1, 3), 2);
  assert.equal(stepIndex(0, -1, 3), 0);
  assert.equal(stepIndex(2, -1, 3), 1);
  assert.equal(stepIndex(-1, 1, 3), 0);
  assert.equal(stepIndex(0, 1, 0), -1);
});
