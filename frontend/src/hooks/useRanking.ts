import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ledgerParams } from "../api/client";
import type { LedgerItem, RatingLines, WindowDays } from "../api/types";
import { NO_TAIL, RANKING_PAGE, hasMore, withPage, type Tail } from "../lib/paging";
import { sortOf } from "../lib/sorts";
import { ledgerFilters, type Route } from "../state/route";
import { useFetch } from "./useFetch";

interface Ranked {
  items: LedgerItem[];
  total: number;
  lines: RatingLines | null;
}

export interface Ranking extends Ranked {
  /** The period the counts cover: the route's, or the sort's own. */
  window: WindowDays;
  /** False while `items` are the previous query's, shown dimmed until this one answers. */
  current: boolean;
  loading: boolean;
  error: string | null;
  retry: () => void;
  /** The first page alone: what the map frames, so that reading further
   *  down the list does not move the map. */
  lead: LedgerItem[];
  /** Whether the list goes on past the rows loaded so far. */
  hasMore: boolean;
  loadingMore: boolean;
  /** Why the next page did not arrive. The rows already shown stay. */
  moreError: string | null;
  /** Asks for the next page; does nothing while one is on its way. */
  loadMore: () => void;
}

const NONE: Ranked = { items: [], total: 0, lines: null };

// The rows after the first page, for the query named by `key`.
interface More {
  key: string | null;
  tail: Tail<LedgerItem>;
  loading: boolean;
  error: string | null;
}

const NO_MORE: More = { key: null, tail: NO_TAIL, loading: false, error: null };
const keyOf = (i: LedgerItem) => i.entity_key;

/**
 * The one ranked list the city view shows, for whichever sort is chosen,
 * read a page at a time down to its last place. The list and the map's pins
 * are both drawn from this, so they cannot disagree. `enabled` is false on
 * the landing page, which has no list.
 */
export function useRanking(route: Route, enabled: boolean): Ranking {
  const sort = sortOf(route.sort);
  const window = route.window ?? sort.window;
  const [attempt, setAttempt] = useState(0);
  const filters = ledgerFilters(route, window);
  // Everything the answer depends on. The city is in it so one city's rows
  // never stand in for another's while the next loads.
  const query = sort.board
    ? `${sort.board}|${window}|${route.cuisine}|${route.borough}`
    : ledgerParams(filters);
  const key = enabled ? `${route.city}|${query}|${attempt}` : null;

  const page = async (offset: number, signal: AbortSignal): Promise<Ranked> => {
    if (sort.board) {
      const d = await api.boards(sort.board, window, route.cuisine, route.borough, signal, RANKING_PAGE, undefined, offset);
      return { items: d.items, total: d.total, lines: d.lines };
    }
    const d = await api.ledger(filters, signal, RANKING_PAGE, undefined, offset);
    return { items: d.items, total: d.total, lines: null };
  };
  const pageRef = useRef(page);
  pageRef.current = page;

  const state = useFetch<Ranked>(key, (signal) => page(0, signal));

  // ---- The pages after the first. They belong to one key: a new sort or
  // filter drops them, and an answer for the old one is thrown away, because
  // an offset in one ordering means nothing in another. ----
  const [more, setMore] = useState<More>(NO_MORE);
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => {
    setMore(NO_MORE);
    return () => ctl.current?.abort();
  }, [key]);

  const first = state.current && state.data && !state.error ? state.data : null;
  const tail = first && more.key === key ? more.tail : NO_TAIL;
  const further = first !== null && hasMore(first.items.length, tail);
  const loadingMore = more.key === key && more.loading;

  const loadMore = useCallback(() => {
    if (!first || !key || !further || loadingMore) return;
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setMore({ key, tail, loading: true, error: null });
    pageRef.current(first.items.length + tail.fetched, c.signal).then(
      (d) => {
        if (!c.signal.aborted) setMore({ key, tail: withPage(first.items, tail, d.items, keyOf, d.total), loading: false, error: null });
      },
      (e: unknown) => {
        if (!c.signal.aborted) setMore({ key, tail, loading: false, error: e instanceof Error ? e.message : String(e) });
      },
    );
  }, [first, key, further, loadingMore, tail]);

  // The previous list only while this one is loading in the same city, and
  // never after a failure: nothing may sit under a heading it was not ranked for.
  const sameCity = state.dataKey?.startsWith(`${route.city}|`) ?? false;
  const shown = state.data && !state.error && (state.current || (state.loading && sameCity)) ? state.data : NONE;
  const items = useMemo(() => (tail.items.length ? [...shown.items, ...tail.items] : shown.items), [shown.items, tail.items]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return {
    items, total: tail.total ?? shown.total, lines: shown.lines, lead: shown.items,
    window, current: state.current, loading: state.loading, error: state.error, retry,
    hasMore: further, loadingMore, moreError: more.key === key ? more.error : null, loadMore,
  };
}
