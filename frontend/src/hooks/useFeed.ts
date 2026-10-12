import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { FeedItem } from "../api/types";

const PAGE = 30;
// The poller lands new posts and comments about every 30 minutes; checking
// each minute shows them soon after without hammering the API.
const POLL_MS = 60_000;
const CHECK_PAGE = 200;
const EMPTY_LOOKBACK_MS = 60 * 60 * 1000;

interface State {
  items: FeedItem[];
  // Arrived since the list was shown, held until the reader takes them, so
  // the list does not jump under someone halfway down it.
  fresh: FeedItem[];
  loading: boolean;
  error: string | null;
  hasMore: boolean;
}

const EMPTY: State = { items: [], fresh: [], loading: true, error: null, hasMore: false };
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Every post and comment, newest first: paged back by "Load more", and
 *  checked for new arrivals every minute. A new search starts over. */
export function useFeed(q: string, placesOnly: boolean) {
  const [state, setState] = useState<State>(EMPTY);
  // Bumped on every new search; a response for an older one is dropped.
  const gen = useRef(0);
  const stateRef = useRef(state);
  stateRef.current = state;
  // When the current search's first page arrived, for a view with no items.
  const loadedAt = useRef(Date.now());

  useEffect(() => {
    const g = ++gen.current;
    const ctl = new AbortController();
    setState(EMPTY);
    api.feed({ q, placesOnly, limit: PAGE }, ctl.signal).then(
      (page) => {
        if (gen.current === g) {
          loadedAt.current = Date.now();
          setState({ items: page.items, fresh: [], loading: false, error: null, hasMore: page.items.length === PAGE });
        }
      },
      (e: unknown) => {
        if (gen.current === g && !ctl.signal.aborted) setState({ ...EMPTY, loading: false, error: message(e) });
      },
    );
    return () => ctl.abort();
  }, [q, placesOnly]);

  const loadMore = useCallback(() => {
    const s = stateRef.current;
    const last = s.items[s.items.length - 1];
    if (!last || s.loading) return;
    const g = gen.current;
    setState((x) => ({ ...x, loading: true, error: null }));
    api.feed({ q, placesOnly, before: last.cursor, limit: PAGE }).then(
      (page) => {
        if (gen.current !== g) return;
        setState((x) => ({
          ...x,
          items: [...x.items, ...page.items],
          loading: false,
          hasMore: page.items.length === PAGE,
        }));
      },
      (e: unknown) => {
        if (gen.current === g) setState((x) => ({ ...x, loading: false, error: message(e) }));
      },
    );
  }, [q, placesOnly]);

  // One check at a time: the interval and a tab coming back into view can fire
  // together, and two with the same cursor would fetch the same items twice.
  const checking = useRef(false);

  const check = useCallback(async () => {
    const s = stateRef.current;
    if (s.loading || checking.current) return;
    const newest = s.fresh[0] ?? s.items[0];
    // An empty view (a search with no matches yet) has no item to continue
    // from, so ask for anything since a little before it was loaded. The
    // margin covers items Reddit stamped before the load that the poller only
    // landed after it; none of them can already be in an empty list.
    let cursor = newest ? newest.cursor : `${new Date(loadedAt.current - EMPTY_LOOKBACK_MS).toISOString()}|`;
    const g = gen.current;
    checking.current = true;
    try {
      // `after` returns the items immediately after the cursor, so a full
      // page means there may be more: keep going until caught up.
      for (;;) {
        const page = await api.feed({ q, placesOnly, after: cursor, limit: CHECK_PAGE });
        if (gen.current !== g) return;
        if (page.items.length > 0) {
          setState((x) => {
            const seen = new Set([...x.fresh, ...x.items].map((i) => i.id));
            const added = page.items.filter((i) => !seen.has(i.id));
            return added.length ? { ...x, fresh: [...added, ...x.fresh] } : x;
          });
        }
        if (page.items.length < CHECK_PAGE) return;
        cursor = page.items[0].cursor;
      }
    } catch {
      // a missed check is retried on the next one
    } finally {
      checking.current = false;
    }
  }, [q, placesOnly]);

  useEffect(() => {
    const id = setInterval(check, POLL_MS);
    // A tab left in the background catches up as soon as it is looked at.
    const onVisible = () => {
      if (document.visibilityState === "visible") check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [check]);

  const showFresh = useCallback(() => {
    setState((x) => (x.fresh.length ? { ...x, items: [...x.fresh, ...x.items], fresh: [] } : x));
  }, []);

  return { ...state, loadMore, showFresh };
}
