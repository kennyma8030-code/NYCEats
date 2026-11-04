import { useCallback, useEffect, useRef, useState } from "react";
import type { Page } from "../api/types";

const PAGE = 50;

interface State<T> {
  // What the items belong to. A page fetched for another key must never
  // render under this one.
  id: string | null;
  items: T[];
  total: number;
  loading: boolean;
  error: string | null;
}

/** A list the server pages, with "Load more". `id` names everything the list
 *  depends on (place, sort, filter): any change restarts from the first page,
 *  because offsets from one ordering mean nothing in another. */
export function usePaged<T>(
  id: string,
  load: (offset: number, limit: number, signal: AbortSignal) => Promise<Page<T>>,
) {
  const [state, setState] = useState<State<T>>({ id: null, items: [], total: 0, loading: false, error: null });
  const ctl = useRef<AbortController | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const fetchPage = useCallback((key: string, offset: number) => {
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setState((s) => ({ ...s, id: key, loading: true, error: null, ...(offset === 0 ? { items: [], total: 0 } : {}) }));
    loadRef.current(offset, PAGE, c.signal).then(
      (page) => {
        if (c.signal.aborted) return;
        setState((s) => ({
          id: key,
          items: offset === 0 ? page.items : [...s.items, ...page.items],
          total: page.total,
          loading: false,
          error: null,
        }));
      },
      (e: unknown) => {
        if (c.signal.aborted) return;
        setState((s) => ({ ...s, loading: false, error: e instanceof Error ? e.message : String(e) }));
      },
    );
  }, []);

  useEffect(() => {
    fetchPage(id, 0);
    return () => ctl.current?.abort();
  }, [id, fetchPage]);

  const loadMore = useCallback(() => {
    if (!state.loading) fetchPage(id, state.items.length);
  }, [id, fetchPage, state.loading, state.items.length]);

  const current = state.id === id;
  return {
    items: current ? state.items : [],
    total: current ? state.total : 0,
    loading: state.loading || !current,
    error: current ? state.error : null,
    hasMore: current && state.items.length < state.total,
    loadMore,
  };
}
