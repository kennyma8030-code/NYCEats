// The three rankings of the city view: what each asks the API for, how it is
// explained, and what a row shows for it. Pure, so the wording can be tested
// on its own (frontend/tests).
import type { BoardId, LedgerItem, RatingLines, WindowDays } from "../api/types";
import { windowOf } from "../state/filters.ts";
import type { SortId } from "../state/route";
import { plural } from "./format.ts";
import { boardExplainer, isRankable, pct, people } from "./rating.ts";

export interface SortDef {
  id: SortId;
  label: string;
  /** The label where there is room for all of it: the landing page's cards. */
  full: string;
  /** A rating board for loved and gems; the ledger answers talked. */
  board: BoardId | null;
  /** The period its counts cover unless the reader picks another. */
  window: WindowDays;
}

// "Highest rated" is the rating's Top board: every place with a stated
// opinion, ranked by how sure we are it is liked. Its id stays `loved`, the
// name it had as "Most loved", because the id is the `sort` in shared URLs.
// The window of a board only sets the mention counts shown in a
// restaurant's numbers, never the ranking.
export const SORTS: SortDef[] = [
  { id: "loved", label: "Highest rated", full: "Highest rated", board: "top", window: 365 },
  { id: "talked", label: "Talked about", full: "Most talked about", board: null, window: 365 },
  { id: "gems", label: "Hidden gems", full: "Hidden gem", board: "gems", window: 365 },
];

export const sortOf = (id: SortId): SortDef => SORTS.find((s) => s.id === id) ?? SORTS[0];

/** One line under the sort saying what the ranking is. */
export function sortNote(id: SortId, window: WindowDays, lines: RatingLines | null): string {
  switch (id) {
    case "loved":
      return boardExplainer("top", lines);
    case "gems":
      return boardExplainer("gems", lines);
    case "talked":
      return `Most mentions over the last ${windowOf(window).long}.`;
  }
}

/** The big number on the right of a row and its caption: always the one
 *  value the list is ranked by, never a blend. A place under the minimum
 *  number of people shows its counts and no percentage, here as on its own
 *  page: "100%" of three people is not a rating. */
export function rowMetric(id: SortId, item: LedgerItem): { big: string; small: string } {
  if (id === "talked") return { big: item.current.toLocaleString(), small: item.current === 1 ? "mention" : "mentions" };
  const r = item.rating;
  if (!r || r.pct_pos == null) return { big: "–", small: "" };
  if (!isRankable(r)) return { big: `${r.pos} of ${people(r)}`, small: "positive" };
  return { big: `${pct(r.pct_pos)}%`, small: plural(people(r), "person", "people") };
}

/** The same number as a sentence fragment, for a card on the landing page:
 *  "98% positive, 56 people", "1,516 mentions", "3 of 3 positive". */
export function cardStat(id: SortId, item: LedgerItem): string {
  const m = rowMetric(id, item);
  if (id === "talked" || (item.rating && !isRankable(item.rating))) return m.small ? `${m.big} ${m.small}` : "";
  return m.small ? `${m.big} positive, ${m.small}` : "";
}
