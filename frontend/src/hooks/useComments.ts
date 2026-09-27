import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Mention } from "../api/types";

const PAGE = 50;

interface State {
  key: string | null;
  items: Mention[];
  total: number;
  loading: boolean;
  error: string | null;
}

/** Top comments for one restaurant, paged by "Load more". */
export function useComments(entityKey: string | null) {
  const [state, setState] = useState<State>({ key: null, items: [], total: 0, loading: false, error: null });
  const ctl = useRef<AbortController | null>(null);

  const fetchPage = useCallback((key: string, offset: number) => {
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setState((s) => ({ ...s, key, loading: true, error: null, ...(offset === 0 ? { items: [], total: 0 } : {}) }));
    api.mentions(key, offset, PAGE, c.signal).then(
      (page) => {
        if (c.signal.aborted) return;
        setState((s) => ({
          key,
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
    if (entityKey) fetchPage(entityKey, 0);
    return () => ctl.current?.abort();
  }, [entityKey, fetchPage]);

  const loadMore = useCallback(() => {
    if (entityKey && !state.loading) fetchPage(entityKey, state.items.length);
  }, [entityKey, fetchPage, state.loading, state.items.length]);

  const current = state.key === entityKey;
  return {
    items: current ? state.items : [],
    total: current ? state.total : 0,
    loading: state.loading || !current,
    error: current ? state.error : null,
    hasMore: current && state.items.length < state.total,
    loadMore,
  };
}
