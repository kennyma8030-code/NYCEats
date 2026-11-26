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
  /** A page came back empty: the list ended, whatever the total said. */
  ended: boolean;
}

export const NO_TAIL: Tail<never> = { items: [], fetched: 0, ended: false };

/**
 * `tail` with the next page added. The rankings are rebuilt while people
 * read them, so a place can move across a page boundary between two
 * requests and come back a second time: it keeps the position it was first
 * shown at, because a row may not appear twice or jump under the reader.
 */
export function withPage<T>(first: T[], tail: Tail<T>, page: T[], keyOf: (item: T) => string): Tail<T> {
  const seen = new Set([...first, ...tail.items].map(keyOf));
  const fresh = page.filter((item) => {
    const key = keyOf(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return { items: [...tail.items, ...fresh], fetched: tail.fetched + page.length, ended: page.length === 0 };
}

/** Whether the server has rows this list has not asked for yet. */
export function hasMore(firstLength: number, tail: Tail<unknown>, total: number): boolean {
  return !tail.ended && firstLength > 0 && firstLength + tail.fetched < total;
}
