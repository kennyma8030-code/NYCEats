// The four rankings of the city view: what each asks the API for, how it is
// explained, and what a row shows for it. Pure, so the wording can be tested
// on its own (frontend/tests).
import type { BoardId, LedgerItem, RatingLines, WindowDays } from "../api/types";
import { windowOf } from "../state/filters.ts";
import type { SortId } from "../state/route";
import { plural, signedCount } from "./format.ts";
import { boardExplainer, pct, people } from "./rating.ts";

export interface SortDef {
  id: SortId;
  label: string;
  /** The label where there is room for all of it: the landing page's cards. */
  full: string;
  /** A rating board for loved and gems; the ledger answers the others. */
  board: BoardId | null;
  /** The period its counts cover unless the reader picks another. */
  window: WindowDays;
}

// "Most loved" is the rating's Top board: the busiest places ranked by how
// sure we are they are liked. The window of a board only sets the mention
// counts shown in a restaurant's numbers, never the ranking.
export const SORTS: SortDef[] = [
  { id: "loved", label: "Most loved", full: "Most loved", board: "top", window: 365 },
  { id: "talked", label: "Talked about", full: "Most talked about", board: null, window: 365 },
  { id: "trending", label: "Trending", full: "Trending", board: null, window: 7 },
  { id: "gems", label: "Hidden gems", full: "Hidden gem", board: "gems", window: 365 },
];

export const sortOf = (id: SortId): SortDef => SORTS.find((s) => s.id === id) ?? SORTS[0];

/** "the last 12 months", or "this week" where that is what people say. */
const span = (w: WindowDays) => (w === 7 ? "this week" : `in the last ${windowOf(w).long}`);
const before = (w: WindowDays) => (w === 7 ? "the week before" : `the ${windowOf(w).long} before`);

/** One line under the sort saying what the ranking is. */
export function sortNote(id: SortId, window: WindowDays, lines: RatingLines | null): string {
  switch (id) {
    case "loved":
      return boardExplainer("top", lines);
    case "gems":
      return boardExplainer("gems", lines);
    case "talked":
      return `Most mentions over the last ${windowOf(window).long}.`;
    case "trending":
      return `Talked about more ${span(window)} than ${before(window)}.`;
  }
}

/** The big number on the right of a row and its caption: always the one
 *  value the list is ranked by, never a blend. */
export function rowMetric(id: SortId, item: LedgerItem): { big: string; small: string } {
  if (id === "talked") return { big: item.current.toLocaleString(), small: item.current === 1 ? "mention" : "mentions" };
  if (id === "trending") {
    return {
      big: signedCount(item.current - item.previous),
      small: `${item.current.toLocaleString()} vs ${plural(item.previous, "mention", "mentions")}`,
    };
  }
  const r = item.rating;
  if (!r || r.pct_pos == null) return { big: "–", small: "" };
  return { big: `${pct(r.pct_pos)}%`, small: plural(people(r), "person", "people") };
}

/** The same number as a sentence fragment, for a card on the landing page:
 *  "98% positive, 56 people", "1,516 mentions", "+11 mentions this week". */
export function cardStat(id: SortId, item: LedgerItem, window: WindowDays): string {
  const m = rowMetric(id, item);
  if (id === "talked") return `${m.big} ${m.small}`;
  if (id === "trending") return `${m.big} mentions ${span(window)}`;
  return m.small ? `${m.big} positive, ${m.small}` : "";
}
