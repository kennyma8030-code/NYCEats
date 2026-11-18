// Which fetched data may be shown under what is on screen.
//
// useFetch keeps the previous result while the next request is in flight, so
// a list can dim instead of blanking. That is only safe if nothing renders the
// previous result as if it were the current one: a list under a heading it was
// not ranked for, or one restaurant's details under another's name. Kept free
// of React and of runtime imports so the rules can be tested on their own
// (frontend/tests).

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
