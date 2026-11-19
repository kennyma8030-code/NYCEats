// The city view's panel widths at the window sizes that matter, and the
// small wording helpers the panels share. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { monthYear, whereLine } from "../src/lib/format.ts";
import { COLUMNS_MIN, MARGIN, cityLayout, mapSides, previewTop, type CityState } from "../src/lib/layout.ts";

const STATES: CityState[] = ["list", "preview", "open", "comments"];

test("nothing reaches past the window's margin at any width above a phone", () => {
  for (const width of [721, 800, 1024, 1280, 1299, 1300, 1440, 1920, 2560]) {
    for (const state of STATES) {
      const l = cityLayout(width, state);
      assert.ok(l.covered <= width - MARGIN, `${state} at ${width}: ends at ${l.covered}`);
      assert.equal(l.phone, false);
    }
  }
});

test("comments get their own column from 1300 and share the restaurant's panel below it", () => {
  assert.equal(cityLayout(COLUMNS_MIN, "comments").columns, true);
  assert.ok(cityLayout(1440, "comments").comments > 0);
  const narrow = cityLayout(1280, "comments");
  assert.equal(narrow.columns, false);
  assert.equal(narrow.comments, 0);
  // The restaurant's panel is wider when it has to hold the comments too.
  assert.ok(narrow.place > cityLayout(1440, "comments").place);
});

test("a restaurant has no comments panel until they are asked for, and is wider for it", () => {
  for (const width of [1024, 1280, 1440, 1920]) {
    const alone = cityLayout(width, "open");
    assert.equal(alone.columns, false, `at ${width}`);
    assert.equal(alone.comments, 0, `at ${width}`);
    assert.ok(alone.place > cityLayout(width, "comments").place, `at ${width}`);
  }
});

test("the list narrows to a strip only while a restaurant is open", () => {
  const list = cityLayout(1440, "list");
  assert.equal(cityLayout(1440, "preview").board, list.board);
  assert.ok(cityLayout(1440, "open").board < list.board / 1.5);
  assert.equal(cityLayout(1440, "comments").board, cityLayout(1440, "open").board);
  assert.equal(list.place, 0);
  assert.equal(list.comments, 0);
});

test("an open restaurant is wider than its preview", () => {
  for (const width of [1024, 1280, 1440]) {
    assert.ok(cityLayout(width, "open").place > cityLayout(width, "preview").place, `at ${width}`);
  }
});

test("a phone is told apart at 720", () => {
  assert.equal(cityLayout(720, "list").phone, true);
  assert.equal(cityLayout(721, "list").phone, false);
});

test("the map always keeps some room to the right of the panels", () => {
  for (const width of [1280, 1300, 1440, 1920]) {
    for (const state of ["open", "comments"] as CityState[]) {
      const s = mapSides(width, cityLayout(width, state));
      assert.ok(width - s.left - s.right >= 100, `${state} at ${width}: ${width - s.left - s.right}`);
    }
  }
});

test("a preview sits level with its row but stays inside the window", () => {
  assert.equal(previewTop(300, 280, 900), 292);
  assert.equal(previewTop(10, 280, 900), MARGIN);
  assert.equal(previewTop(850, 280, 900), 900 - MARGIN - 280);
  // Taller than the window: pinned to the top margin.
  assert.equal(previewTop(400, 2000, 900), MARGIN);
});

test("a place is described without separators", () => {
  assert.equal(whereLine("Pizza", "Greenwich Village"), "Pizza, Greenwich Village");
  assert.equal(whereLine(null, "Flushing"), "Flushing");
  assert.equal(whereLine("Thai", null), "Thai");
  assert.equal(whereLine(null, undefined), "");
});

test("a summary's date reads as a month and a year", () => {
  assert.equal(monthYear("2026-11-08T05:06:20.901849Z"), "November 2026");
  assert.equal(monthYear(null), "");
  assert.equal(monthYear("not a date"), "");
});
