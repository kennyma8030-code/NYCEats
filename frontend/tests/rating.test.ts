// The wording of a rating, without a browser. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { boardExplainer, boardMetric, complaintPhrase, headline, isRankable, rankableCategories } from "../src/lib/rating.ts";
import type { Rating, RatingLines } from "../src/api/types.ts";

const rating: Rating = {
  window_days: 365, pos: 178, neg: 34, neutral: 10, endorse: 162, superlative: 40, recommenders: 340,
  pct_pos: 0.8396, lb: 0.8, neg_share: 0.25, rankable: true, busy: true, badge: "consensus", last_voice: null,
  categories: {
    taste: { pos: 90, neg: 10, neutral: 2, pct_pos: 0.9, lb: 0.85, rankable: true },
    value: { pos: 3, neg: 2, neutral: 0, pct_pos: 0.6, lb: 0.3, rankable: false },
    wait: { pos: 20, neg: 40, neutral: 1, pct_pos: 0.33, lb: 0.25, rankable: true },
  },
};
const lines = { busy_line: 78, min_category_rated: 8 } as RatingLines;

test("headline reads as one line", () => {
  assert.equal(headline(rating), "84% positive · 212 people · recommended by 340");
});

test("complaint share is plain language", () => {
  assert.equal(complaintPhrase(0.25), "1 in 4 complain");
  assert.equal(complaintPhrase(0.02), "Almost no one complains");
  assert.equal(complaintPhrase(0.6), "Most of them complain");
  assert.equal(complaintPhrase(null), null);
});

test("only rankable categories, most people first", () => {
  assert.deepEqual(rankableCategories(rating).map((c) => c.key), ["taste", "wait"]);
});

test("not rankable means no percentage", () => {
  assert.equal(isRankable(null), false);
  assert.equal(isRankable({ ...rating, rankable: false }), false);
  assert.equal(isRankable(rating), true);
});

test("board explainers use the cut-offs", () => {
  assert.match(boardExplainer("top", lines), /at least 78 people/);
  assert.match(boardExplainer("gems", lines), /Under 78 recommenders/);
  assert.match(boardExplainer("popular", null), /above the median/);
});

test("board rows lead with what the board ranks by", () => {
  assert.equal(boardMetric("popular", rating).big, "340");
  assert.equal(boardMetric("top", rating).big, "84%");
  assert.equal(boardMetric("taste", rating).big, "90%");
});
