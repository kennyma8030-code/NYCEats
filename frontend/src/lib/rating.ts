// How a rating is put into words. Pure and free of runtime imports so the
// wording can be tested on its own (frontend/tests).
import type { Badge, BoardId, Rating, RatingCategory, RatingLines } from "../api/types";

const n = (x: number) => x.toLocaleString();

/** A fraction as a whole percent: 0.836 -> 84. */
export const pct = (f: number) => Math.round(f * 100);

/** People who stated an opinion, for or against. Neutral and bare
 *  recommendations are not in it: they are not a vote either way. */
export const people = (r: { pos: number; neg: number }) => r.pos + r.neg;

/** Whether the rating can say anything. A null rating or one under the
 *  minimum number of people shows counts only, never a percentage or badge. */
export const isRankable = (r: Rating | null | undefined): boolean => !!r && r.rankable && r.pct_pos != null;

export const BADGE_LABEL: Record<Badge, string> = {
  consensus: "Consensus pick",
  hidden_gem: "Hidden gem",
  overhyped_mixed: "Overhyped / mixed",
};

export const CATEGORY_LABEL: Record<RatingCategory, string> = {
  taste: "Taste",
  value: "Value",
  service: "Service",
  atmosphere: "Atmosphere",
  wait: "Wait",
};

/** "84% positive · 212 people · recommended by 340". */
export function headline(r: Rating): string {
  const bits: string[] = [];
  if (r.pct_pos != null) bits.push(`${pct(r.pct_pos)}% positive`);
  bits.push(`${n(people(r))} ${people(r) === 1 ? "person" : "people"}`);
  bits.push(`recommended by ${n(r.recommenders)}`);
  return bits.join(" · ");
}

/** The complaint share in plain words, over the same people the headline
 *  counts (pos + neg): "1 in 4 complain" while that reads naturally, a percent
 *  from 40% up. Null when nobody complains or nobody has an opinion. */
export function complaintPhrase(r: { pos: number; neg: number }): string | null {
  const total = people(r);
  if (total === 0 || r.neg === 0) return null;
  const share = r.neg / total;
  if (share < 0.05) return "Almost no one complains";
  if (share < 0.4) return `1 in ${Math.round(1 / share)} complain`;
  if (share >= 0.45 && share <= 0.55) return "About half complain";
  return `${pct(share)}% complain`;
}

/** The categories worth showing: rankable ones, most people first. */
export function rankableCategories(r: Rating): { key: RatingCategory; pos: number; neg: number; pct: number; people: number }[] {
  return (Object.keys(CATEGORY_LABEL) as RatingCategory[])
    .flatMap((key) => {
      const c = r.categories[key];
      return c && c.rankable && c.pct_pos != null ? [{ key, pos: c.pos, neg: c.neg, pct: pct(c.pct_pos), people: people(c) }] : [];
    })
    .sort((a, b) => b.people - a.people);
}

/** One line under the tabs saying what the ranking is. The cut-offs come from
 *  the API (`lines`) so they say what was true at the last rebuild. */
export function boardExplainer(board: BoardId, lines: RatingLines | null): string {
  const busy = lines?.busy_line != null ? n(lines.busy_line) : "many";
  switch (board) {
    case "top":
      return `Places at least ${busy} people recommend, ranked by how sure we are they're liked.`;
    case "popular":
      return "Most recommended, among places rated above the median.";
    case "gems":
      return `Under ${busy} recommenders and near-unanimous praise.`;
    default: {
      const min = lines?.min_category_rated;
      return `Ranked by how sure we are people like the ${CATEGORY_LABEL[board].toLowerCase()}${
        min ? `, among places at least ${min} people have judged on it` : ""
      }.`;
    }
  }
}

/** What a board row shows on the right: one big number and its caption.
 *  Popular leads with the volume it ranks by, the others with % positive,
 *  and a category board with that category's. */
export function boardMetric(board: BoardId, r: Rating): { big: string; small: string } {
  if (board === "popular") {
    return { big: n(r.recommenders), small: r.pct_pos != null ? `recommend · ${pct(r.pct_pos)}% positive` : "recommend" };
  }
  const cat = board === "top" || board === "gems" ? null : r.categories[board];
  if (board !== "top" && board !== "gems" && cat && cat.pct_pos != null) {
    return { big: `${pct(cat.pct_pos)}%`, small: `${n(people(cat))} people · ${CATEGORY_LABEL[board].toLowerCase()}` };
  }
  return {
    big: r.pct_pos != null ? `${pct(r.pct_pos)}%` : "–",
    small: `${n(people(r))} people · ${n(r.recommenders)} recommend`,
  };
}
