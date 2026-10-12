import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { FeedItem } from "../api/types";

const PAGE = 30;
// The poller lands new posts and comments about every 30 minutes; checking
// each minute shows them soon after without hammering the API.
const POLL_MS = 60_000;

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

  useEffect(() => {
    const g = ++gen.current;
    const ctl = new AbortController();
    setState(EMPTY);
    api.feed({ q, placesOnly, limit: PAGE }, ctl.signal).then(
      (page) => {
        if (gen.current === g) {
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

  const check = useCallback(() => {
    const s = stateRef.current;
    const newest = s.fresh[0] ?? s.items[0];
    if (!newest || s.loading) return;
    const g = gen.current;
    api.feed({ q, placesOnly, after: newest.cursor, limit: 200 }).then(
      (page) => {
        if (gen.current !== g || page.items.length === 0) return;
        setState((x) => ({ ...x, fresh: [...page.items, ...x.fresh] }));
      },
      () => {}, // a missed check is retried on the next one
    );
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
