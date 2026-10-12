import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { CommentSort, Mention } from "../api/types";

const PAGE = 50;

interface State {
  // What the items belong to. A page fetched under another restaurant or
  // another sort must never render under this one.
  key: string | null;
  sort: CommentSort | null;
  items: Mention[];
  total: number;
  loading: boolean;
  error: string | null;
}

/** One restaurant's comments in the chosen order, paged by "Load more". */
export function useComments(entityKey: string | null, sort: CommentSort) {
  const [state, setState] = useState<State>({ key: null, sort: null, items: [], total: 0, loading: false, error: null });
  const ctl = useRef<AbortController | null>(null);

  const fetchPage = useCallback((key: string, order: CommentSort, offset: number) => {
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setState((s) => ({ ...s, key, sort: order, loading: true, error: null, ...(offset === 0 ? { items: [], total: 0 } : {}) }));
    api.mentions(key, order, offset, PAGE, c.signal).then(
      (page) => {
        if (c.signal.aborted) return;
        setState((s) => ({
          key,
          sort: order,
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

  // A new sort restarts from the first page: offsets from one ordering mean
  // nothing in another, so appending would duplicate and skip comments.
  useEffect(() => {
    if (entityKey) fetchPage(entityKey, sort, 0);
    return () => ctl.current?.abort();
  }, [entityKey, sort, fetchPage]);

  const loadMore = useCallback(() => {
    if (entityKey && !state.loading) fetchPage(entityKey, sort, state.items.length);
  }, [entityKey, sort, fetchPage, state.loading, state.items.length]);

  const current = state.key === entityKey && state.sort === sort;
  return {
    items: current ? state.items : [],
    total: current ? state.total : 0,
    loading: state.loading || !current,
    error: current ? state.error : null,
    hasMore: current && state.items.length < state.total,
    loadMore,
  };
}
