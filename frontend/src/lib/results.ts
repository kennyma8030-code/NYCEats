// What a search's answer says about itself, and which of a result's comments
// are still to be read. Pure and free of React so the rules can be tested on
// their own (frontend/tests).
import type { SearchItem, SearchResponse } from "../api/types";

/** How many comments one request for the rest asks for (the API's limit). */
export const COMMENTS_PAGE = 50;

/** What the count beside every place is a count of. One sentence for each
 *  way a list can be ranked, so a list matched on words is never described
 *  as one matched by meaning. */
export function countedBy(d: Pick<SearchResponse, "semantic" | "ranked_by">): string {
  if (d.ranked_by !== "matching_people") return "brought them up";
  return d.semantic === "text" ? "used these words about them" : "wrote a matching comment";
}

/** The comments a place's count counts: all of them when the search named
 *  them, otherwise the ones it came with (the board's own count, which the
 *  place's page opens in full). */
export const commentTotal = (it: SearchItem) => it.mention_ids?.length ?? it.comments.length;

/** The next ids to ask for, given the mention ids already on screen: the
 *  result's own order, skipping what is shown, one page at a time. */
export function nextComments(it: SearchItem, shown: number[], page = COMMENTS_PAGE): number[] {
  const have = new Set(shown);
  return (it.mention_ids ?? []).filter((id) => !have.has(id)).slice(0, page);
}

/** What the button under a result's comments says, or null when every
 *  comment the count counts is already on screen. */
export function moreLabel(it: SearchItem, shown: number, page = COMMENTS_PAGE): string | null {
  const total = commentTotal(it);
  const left = total - shown;
  if (left <= 0) return null;
  return left <= page ? `Show all ${total.toLocaleString()} comments` : `Show ${page} more of ${total.toLocaleString()} comments`;
}
