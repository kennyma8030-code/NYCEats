import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { LedgerItem } from "../api/types";
import { sortOf } from "../lib/sorts";
import { wallPlaces, wallPool, wallQuotes, type WallCard } from "../lib/wall";
import { HOME } from "../state/city";
import { DEFAULT_FILTERS } from "../state/filters";
import type { SortId } from "../state/route";

// The most the feed gives at once: of these, a couple of dozen read well as one line.
const FEED = 200;

const quiet = <T,>(p: Promise<T>, fallback: T): Promise<T> => p.catch(() => fallback);

/**
 * The cards for the landing page's wall: New York's recent comments that
 * name a place, and the top of its three rankings. Read once per visit and
 * dealt out when everything has answered, because cards arriving one source
 * at a time would make the columns jump. A source that fails is left out;
 * if they all do the wall is simply empty behind the title.
 */
export function useWall(enabled: boolean): WallCard[] {
  const [pool, setPool] = useState<WallCard[]>([]);

  useEffect(() => {
    if (!enabled || pool.length) return;
    const ctl = new AbortController();
    const ledger = (id: SortId): Promise<LedgerItem[]> =>
      quiet(
        api.ledger({ ...DEFAULT_FILTERS, category: id === "trending" ? "trending" : "top", window: sortOf(id).window }, ctl.signal, 12, HOME)
          .then((d) => d.items),
        [],
      );
    Promise.all([
      quiet(api.feed({ placesOnly: true, limit: FEED }, ctl.signal, HOME).then((d) => d.items), []),
      quiet(api.boards("top", 30, "", "", ctl.signal, 12, HOME).then((d) => d.items), []),
      ledger("talked"),
      ledger("trending"),
    ]).then(([feed, loved, talked, trending]) => {
      if (ctl.signal.aborted) return;
      setPool(wallPool(wallQuotes(feed, HOME), [
        wallPlaces("trending", trending), wallPlaces("loved", loved), wallPlaces("talked", talked),
      ]));
    });
    return () => ctl.abort();
  }, [enabled, pool.length]);

  return pool;
}
