import { useCallback, useState } from "react";
import { api, ledgerParams } from "../api/client";
import type { LedgerItem, RatingLines, WindowDays } from "../api/types";
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
}

const NONE: Ranked = { items: [], total: 0, lines: null };

/**
 * The one ranked list the city view shows, for whichever sort is chosen.
 * The list and the map's pins are both drawn from this, so they cannot
 * disagree. `enabled` is false on the landing page, which has no list.
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

  const state = useFetch<Ranked>(key, async (signal) => {
    if (sort.board) {
      const d = await api.boards(sort.board, window, route.cuisine, route.borough, signal);
      return { items: d.items, total: d.total, lines: d.lines };
    }
    const d = await api.ledger(filters, signal);
    return { items: d.items, total: d.total, lines: null };
  });

  // The previous list only while this one is loading in the same city, and
  // never after a failure: nothing may sit under a heading it was not ranked for.
  const sameCity = state.dataKey?.startsWith(`${route.city}|`) ?? false;
  const shown = state.data && !state.error && (state.current || (state.loading && sameCity)) ? state.data : NONE;
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { ...shown, window, current: state.current, loading: state.loading, error: state.error, retry };
}
