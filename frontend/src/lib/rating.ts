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

// What each category is called when it is praised and when it is complained of.
const LIKED_AS: Record<RatingCategory, string> = {
  taste: "The food", value: "Value", service: "Service", atmosphere: "The room", wait: "A short wait",
};
const FAULTED_AS: Record<RatingCategory, string> = {
  taste: "The food", value: "Prices", service: "Service", atmosphere: "The room", wait: "The wait",
};

// A category most people are happy with is something the place is liked
// for; one that splits opinion, or worse, is a complaint worth knowing about.
const LIKED_FROM = 60;

export interface Verdict {
  key: RatingCategory;
  label: string;
  /** The share, as a whole percent, of the side this verdict is on. */
  pct: number;
}

/** A place's rated categories as two short lists: what it is liked for and
 *  what people complain about, each strongest first. One number a row: the
 *  share who were positive in the first list, negative in the second. */
export function goodToKnow(r: Rating): { liked: Verdict[]; complaints: Verdict[] } {
  const liked: Verdict[] = [];
  const complaints: Verdict[] = [];
  for (const c of rankableCategories(r)) {
    if (c.pct >= LIKED_FROM) liked.push({ key: c.key, label: LIKED_AS[c.key], pct: c.pct });
    else complaints.push({ key: c.key, label: FAULTED_AS[c.key], pct: 100 - c.pct });
  }
  const strongest = (a: Verdict, b: Verdict) => b.pct - a.pct;
  return { liked: liked.sort(strongest), complaints: complaints.sort(strongest) };
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
