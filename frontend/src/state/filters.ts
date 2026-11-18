import type { Algo, Category, Flaw, Need, WindowDays } from "../api/types";

/** What /api/ledger ranks under. The city view builds one of these from the
 *  route (state/route.ts) for the sorts the ledger answers. */
export interface Filters {
  algo: Algo;
  topic: string;
  category: Category;
  window: WindowDays;
  cuisine: string;
  borough: string;
  needs: Need[];
  flaws: Flaw[];
}

const CATEGORIES: Category[] = ["trending", "top", "gems"];

/** `long` completes "the last ...": the last 7 days, the last month. */
export const WINDOWS: { d: WindowDays; short: string; long: string }[] = [
  { d: 7, short: "7D", long: "7 days" },
  { d: 14, short: "14D", long: "14 days" },
  { d: 30, short: "1M", long: "month" },
  { d: 90, short: "3M", long: "3 months" },
  { d: 180, short: "6M", long: "6 months" },
  { d: 365, short: "1Y", long: "12 months" },
];

export const NEEDS: { k: Need; label: string }[] = [
  { k: "value", label: "Good value" },
  { k: "atmosphere", label: "Great room" },
  { k: "service", label: "Good service" },
  { k: "wait", label: "Short wait" },
];

// Opposites of NEEDS, plus food. The API keeps the worst tenth of places for
// each, measured live, since the scores do not sit evenly around zero.
export const FLAWS: { k: Flaw; label: string }[] = [
  { k: "food", label: "Bad food" },
  { k: "value", label: "Poor value" },
  { k: "atmosphere", label: "Unpleasant room" },
  { k: "service", label: "Bad service" },
  { k: "wait", label: "Long wait" },
];

export const DEFAULT_FILTERS: Filters = {
  algo: "v1", topic: "", category: "trending", window: 7, cuisine: "", borough: "", needs: [], flaws: [],
};

export const windowOf = (d: WindowDays) => WINDOWS.find((w) => w.d === d) ?? WINDOWS[0];
export const isWindow = (n: number): n is WindowDays => WINDOWS.some((w) => w.d === n);

const uniq = <T,>(xs: T[]) => [...new Set(xs)];

/** Filters from a query string. Repeated needs and flaws collapse to one, as
 *  the API collapses them: ?need=value&need=value is one filter, and a list
 *  that kept both would never match the response that echoes one. */
export function filtersFromQuery(search: string, stored: Algo | null): Filters {
  const p = new URLSearchParams(search);
  const cat = p.get("category");
  const win = Number(p.get("window"));
  const algo = p.get("algo");
  return {
    algo: algo === "v1" || algo === "v2" ? algo : stored ?? DEFAULT_FILTERS.algo,
    topic: p.get("topic") ?? "",
    category: CATEGORIES.includes(cat as Category) ? (cat as Category) : DEFAULT_FILTERS.category,
    window: isWindow(win) ? win : DEFAULT_FILTERS.window,
    cuisine: p.get("cuisine") ?? "",
    borough: p.get("borough") ?? "",
    needs: uniq(p.getAll("need").filter((n): n is Need => NEEDS.some((x) => x.k === n))),
    flaws: uniq(p.getAll("flaw").filter((n): n is Flaw => FLAWS.some((x) => x.k === n))),
  };
}
