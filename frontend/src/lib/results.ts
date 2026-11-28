// What a search's answer says about itself, and which of a result's comments
// are still to be read. Pure and free of React so the rules can be tested on
// their own (frontend/tests).
import type { Mention, SearchItem, SearchResponse } from "../api/types";

/** How many comments one request for the rest asks for (the API's limit). */
export const COMMENTS_PAGE = 50;

/** What the count beside every place is a count of. One sentence for each
 *  way a list can be ranked, so a list matched on words is never described
 *  as one matched by meaning. */
export function countedBy(d: Pick<SearchResponse, "semantic" | "ranked_by">): string {
  if (d.ranked_by !== "matching_people") return "brought them up";
  return d.semantic === "text" ? "used these words about them" : "wrote a matching comment";
}

/** The comments a place's count counts: the server's own number when it
 *  gives one (a text match names only the first of its comments), else all
 *  it named, else the ones it came with (the board's own count, which the
 *  place's page opens in full). */
export const commentTotal = (it: SearchItem) => it.comment_count ?? it.mention_ids?.length ?? it.comments.length;

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

/** What has been read of one result's comments beyond the ones it came with. */
export interface Loaded {
  extra: Mention[];
  /** Ids asked for that did not come back (a comment gone since the search):
   *  counted as read, so the button does not ask for them forever. */
  missing: number[];
  /** How many comments past the named ids have been asked for by position. */
  paged: number;
  /** Comments the count counts that will never be shown: a page came back
   *  short, or held one already on screen. Counted as read, as `missing` is. */
  short: number;
}

export const NOTHING_LOADED: Loaded = { extra: [], missing: [], paged: 0, short: 0 };

/** How many of the result's comments are accounted for. */
export const seenCount = (it: SearchItem, l: Loaded) => it.comments.length + l.extra.length + l.missing.length + l.short;

/** The next request for a result's comments: the ids it named and are not
 *  yet shown, and after those, for a text match that counts more than it
 *  named, the next page by position. Null when there is nothing to ask. */
export function nextRequest(
  it: SearchItem, l: Loaded, canPage: boolean, page = COMMENTS_PAGE,
): { ids: number[] } | { offset: number; limit: number } | null {
  const ids = nextComments(it, [...it.comments, ...l.extra].map((c) => c.mention_id).concat(l.missing), page);
  if (ids.length) return { ids };
  const left = commentTotal(it) - seenCount(it, l);
  if (left <= 0 || !canPage || it.mention_ids === null) return null;
  return { offset: it.mention_ids.length + l.paged, limit: Math.min(page, left) };
}

/** After asking for `ids`: the rows that came, and the ids that did not. */
export function afterIds(l: Loaded, ids: number[], rows: Mention[]): Loaded {
  const got = new Set(rows.map((r) => r.mention_id));
  return { ...l, extra: [...l.extra, ...rows], missing: [...l.missing, ...ids.filter((id) => !got.has(id))] };
}

/** After asking for a page of `limit` by position. A page that comes back
 *  short is the end of the comments, whatever the count said when the search
 *  ran, so what is left of it is written off rather than asked for again. */
export function afterPage(it: SearchItem, l: Loaded, limit: number, rows: Mention[]): Loaded {
  const have = new Set([...it.comments, ...l.extra].map((c) => c.mention_id));
  const fresh = rows.filter((r) => !have.has(r.mention_id));
  const next = { ...l, extra: [...l.extra, ...fresh], paged: l.paged + limit, short: l.short + rows.length - fresh.length };
  if (rows.length < limit) next.short += Math.max(0, commentTotal(it) - seenCount(it, next));
  return next;
}

/** Which result's comments a Loaded belongs to: the place, and enough of
 *  what the answer said of it that a later, different answer to the same
 *  query does not inherit comments read for this one. */
export const resultId = (it: SearchItem) => `${it.entity_key}|${commentTotal(it)}|${it.comments[0]?.mention_id ?? ""}`;

/**
 * The comments read for the results of one answer, kept outside the list
 * that draws them. The list is taken down while a restaurant is open (a
 * narrow strip of names beside it, or nothing at all on a phone); without
 * this, coming back to the search meant asking for every opened comment
 * again. One answer at a time: a new search forgets the last one's.
 */
export function loadedStore() {
  let answer: string | null = null;
  let rows = new Map<string, Loaded>();
  return {
    get: (of: string, id: string): Loaded => (of === answer ? rows.get(id) : undefined) ?? NOTHING_LOADED,
    set(of: string, id: string, l: Loaded) {
      if (of !== answer) {
        answer = of;
        rows = new Map();
      }
      rows.set(id, l);
    },
  };
}

export const loaded = loadedStore();
