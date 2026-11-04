import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { CommentSort, Mention, RatingCategory, Voice } from "../api/types";

const PAGE = 50;

interface State {
  // What the items belong to. A page fetched for another place, voice,
  // category or sort must never render under this one.
  id: string | null;
  items: Mention[];
  total: number;
  loading: boolean;
  error: string | null;
}

/** The comments behind one count of a rating, paged by "Load more". */
export function useVoices(entityKey: string, voice: Voice, category: RatingCategory | null, sort: CommentSort) {
  const id = `${entityKey}|${voice}|${category ?? ""}|${sort}`;
  const [state, setState] = useState<State>({ id: null, items: [], total: 0, loading: false, error: null });
  const ctl = useRef<AbortController | null>(null);

  const fetchPage = useCallback(
    (offset: number) => {
      ctl.current?.abort();
      const c = new AbortController();
      ctl.current = c;
      setState((s) => ({ ...s, id, loading: true, error: null, ...(offset === 0 ? { items: [], total: 0 } : {}) }));
      api.voices(entityKey, voice, category, sort, offset, PAGE, c.signal).then(
        (page) => {
          if (c.signal.aborted) return;
          setState((s) => ({
            id,
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
    },
    [id, entityKey, voice, category, sort],
  );

  // Offsets from one ordering or filter mean nothing in another, so any
  // change restarts from the first page.
  useEffect(() => {
    fetchPage(0);
    return () => ctl.current?.abort();
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (!state.loading) fetchPage(state.items.length);
  }, [fetchPage, state.loading, state.items.length]);

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
