// How a ranked list grows a page at a time. Pure and free of runtime
// imports so the rules can be tested on their own (frontend/tests).

/** Rows asked for at a time: about four screens of the list. */
export const RANKING_PAGE = 50;

/** The most rows the map draws pins for. Each pin is an element the map
 *  moves on every frame, and a list can run past ten thousand rows. */
export const PIN_LIMIT = 500;

/** The rows after the first page, and how far the server has been read. */
export interface Tail<T> {
  items: T[];
  /** Rows received after the first page, repeats included: with the first
   *  page's length, the offset the next page is asked from. */
  fetched: number;
  /** A page came back short or empty: the list ended, whatever any total said. */
  ended: boolean;
  /** The size of the whole list as the latest page gave it, null before one
   *  has. The list changes while it is read, so the newest count is the one shown. */
  total: number | null;
}

export const NO_TAIL: Tail<never> = { items: [], fetched: 0, ended: false, total: null };

/**
 * `tail` with the next page added. The rankings are rebuilt while people
 * read them, so a place can move across a page boundary between two
 * requests and come back a second time: it keeps the position it was first
 * shown at, because a row may not appear twice or jump under the reader.
 * `total` is what this page said the whole list holds; a page past the end
 * may not know (0), and the last known count is kept.
 */
export function withPage<T>(
  first: T[], tail: Tail<T>, page: T[], keyOf: (item: T) => string, total = 0, size = RANKING_PAGE,
): Tail<T> {
  const seen = new Set([...first, ...tail.items].map(keyOf));
  const fresh = page.filter((item) => {
    const key = keyOf(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return {
    items: [...tail.items, ...fresh],
    fetched: tail.fetched + page.length,
    // By what the server sent, repeats and all: a full page of repeats is
    // not the end, and a short one is, however many rows are showing.
    ended: page.length < size,
    total: total > 0 ? total : tail.total,
  };
}

/** Whether the server may have rows this list has not asked for yet. Only a
 *  page that came back short says it has none: a total was counted at one
 *  moment and the list has moved since, so a list is not ended by reaching
 *  it. A list of exactly a whole number of pages costs one empty request. */
export function hasMore(firstLength: number, tail: Tail<unknown>, size = RANKING_PAGE): boolean {
  return !tail.ended && firstLength >= size;
}
