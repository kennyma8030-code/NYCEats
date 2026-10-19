// Which fetched data may be shown under what is on screen.
//
// useFetch keeps the previous result while the next request is in flight, so
// a list can dim instead of blanking. That is only safe if nothing renders the
// previous result as if it were the current one: a list under a heading it was
// not ranked for, or one restaurant's details under another's name. Kept free
// of React and of runtime imports so the rules can be tested on their own
// (frontend/tests).
import type { LedgerItem, LedgerResponse } from "../api/types";
import type { Filters } from "../state/filters";

// As sets: the API de-duplicates needs and flaws before echoing them, so
// ["value", "value"] and ["value"] are the same filter.
const sameSet = (a: readonly string[], b: readonly string[]) => {
  const x = new Set(a);
  const y = new Set(b);
  return x.size === y.size && [...x].every((v) => y.has(v));
};

/** Whether a ledger response was ranked under exactly these filters, read
 *  from the parameters the API echoes back. The topic is compared trimmed,
 *  because the API trims it before ranking. */
export function ledgerMatches(d: LedgerResponse, f: Filters): boolean {
  return (
    d.category === f.category &&
    d.window_days === f.window &&
    d.algo === f.algo &&
    (d.topic ?? "") === f.topic.trim() &&
    (d.cuisine ?? "") === f.cuisine &&
    (d.borough ?? "") === f.borough &&
    sameSet(d.needs ?? [], f.needs) &&
    sameSet(d.flaws ?? [], f.flaws)
  );
}

/** The rows a ledger list may show.
 *
 *  Its own response's rows, always. The previous filters' rows only while
 *  the request for these is still in flight, when the list is drawn dimmed
 *  and aria-busy so it reads as "updating", and the rows that stay can slide
 *  to their new places. Never after an error, and never once the request has
 *  settled on something that is not for these filters. */
export function visibleLedgerItems(
  d: LedgerResponse | null,
  f: Filters,
  loading: boolean,
  error: string | null,
): { items: LedgerItem[]; current: boolean } {
  if (error || !d) return { items: [], current: false };
  if (ledgerMatches(d, f)) return { items: d.items, current: true };
  return { items: loading ? d.items : [], current: false };
}

export interface FetchState<T> {
  /** The last successful result, which may belong to a previous key while
   *  the next request is in flight. Check `current` before showing it as
   *  the answer for the key asked about now. */
  data: T | null;
  /** The key `data` was loaded for. */
  dataKey: string | null;
  /** Whether `data` is the answer for the key asked about right now. */
  current: boolean;
  error: string | null;
  loading: boolean;
}

/** useFetch's internal state. */
export interface FetchInner<T> {
  // The key the latest request -- and so `error` and `loading` -- is about.
  key: string | null;
  data: T | null;
  dataKey: string | null;
  error: string | null;
  loading: boolean;
}

/** What useFetch reports for `key`, given its state. Between a key change
 *  and its effect running, the state still describes the old key: that is
 *  reported as loading with no error, never as a settled answer. */
export function fetchView<T>(s: FetchInner<T>, key: string | null): FetchState<T> {
  const asked = s.key === key;
  return {
    data: s.data,
    dataKey: s.dataKey,
    current: key !== null && s.dataKey === key,
    error: asked ? s.error : null,
    loading: key !== null && (!asked || s.loading),
  };
}
