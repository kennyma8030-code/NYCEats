import { useCallback, useEffect, useState } from "react";
import type { Algo, Category, Flaw, Need, WindowDays } from "../api/types";

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

export const CATEGORIES: { k: Category; label: string; hint: string }[] = [
  { k: "trending", label: "Trending", hint: "Talked about more than the period before" },
  { k: "top", label: "Top", hint: "Most talked about" },
  { k: "gems", label: "Hidden gems", hint: "Loved, but not many people know yet" },
];

export const WINDOWS: { d: WindowDays; short: string; long: string }[] = [
  { d: 7, short: "7D", long: "7 days" },
  { d: 14, short: "14D", long: "14 days" },
  { d: 30, short: "1M", long: "month" },
  { d: 90, short: "3M", long: "3 months" },
  { d: 180, short: "6M", long: "6 months" },
  { d: 365, short: "1Y", long: "year" },
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

// The ranking choice outlives a page load, so a comparison is not lost on
// reload; a link that names one still wins.
const ALGO_KEY = "nyceats.algo";
function storedAlgo(): Algo | null {
  try {
    const v = localStorage.getItem(ALGO_KEY);
    return v === "v1" || v === "v2" ? v : null;
  } catch {
    return null;
  }
}
function storeAlgo(a: Algo) {
  try {
    localStorage.setItem(ALGO_KEY, a);
  } catch {
    /* private mode */
  }
}

export const windowOf = (d: WindowDays) => WINDOWS.find((w) => w.d === d) ?? WINDOWS[0];
export const categoryOf = (k: Category) => CATEGORIES.find((c) => c.k === k) ?? CATEGORIES[0];

// The URL is the source of truth on load, so a filtered view can be shared.
function fromUrl(): Filters {
  const p = new URLSearchParams(window.location.search);
  const cat = p.get("category");
  const win = Number(p.get("window"));
  const algo = p.get("algo");
  return {
    algo: algo === "v1" || algo === "v2" ? algo : storedAlgo() ?? DEFAULT_FILTERS.algo,
    topic: p.get("topic") ?? "",
    category: CATEGORIES.some((c) => c.k === cat) ? (cat as Category) : DEFAULT_FILTERS.category,
    window: WINDOWS.some((w) => w.d === win) ? (win as WindowDays) : DEFAULT_FILTERS.window,
    cuisine: p.get("cuisine") ?? "",
    borough: p.get("borough") ?? "",
    needs: p.getAll("need").filter((n): n is Need => NEEDS.some((x) => x.k === n)),
    flaws: p.getAll("flaw").filter((n): n is Flaw => FLAWS.some((x) => x.k === n)),
  };
}

function toUrl(f: Filters) {
  const p = new URLSearchParams();
  if (f.algo !== DEFAULT_FILTERS.algo) p.set("algo", f.algo);
  if (f.topic) p.set("topic", f.topic);
  if (f.category !== DEFAULT_FILTERS.category) p.set("category", f.category);
  if (f.window !== DEFAULT_FILTERS.window) p.set("window", String(f.window));
  if (f.cuisine) p.set("cuisine", f.cuisine);
  if (f.borough) p.set("borough", f.borough);
  f.needs.forEach((n) => p.append("need", n));
  f.flaws.forEach((n) => p.append("flaw", n));
  // The open restaurant is not a filter, but it shares the query string.
  const r = new URLSearchParams(window.location.search).get("r");
  if (r) p.set("r", r);
  const qs = p.toString();
  window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

/** The restaurant open in the detail panel, as ?r=, so it can be shared. */
export function restaurantFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("r");
}

export function setRestaurantInUrl(key: string | null) {
  const p = new URLSearchParams(window.location.search);
  if (key) p.set("r", key);
  else p.delete("r");
  const qs = p.toString();
  window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

export function activeFilterCount(f: Filters) {
  return (f.topic ? 1 : 0) + (f.cuisine ? 1 : 0) + (f.borough ? 1 : 0) + f.needs.length + f.flaws.length;
}

export function useFilters() {
  const [filters, setFilters] = useState<Filters>(fromUrl);
  useEffect(() => toUrl(filters), [filters]);
  useEffect(() => storeAlgo(filters.algo), [filters.algo]);

  const update = useCallback((patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch })), []);
  // "Good value" and "Poor value" cannot both hold, so ticking one clears
  // the other (the API rejects the pair).
  const toggleNeed = useCallback(
    (n: Need) =>
      setFilters((f) =>
        f.needs.includes(n)
          ? { ...f, needs: f.needs.filter((x) => x !== n) }
          : { ...f, needs: [...f.needs, n], flaws: f.flaws.filter((x) => x !== n) },
      ),
    [],
  );
  const toggleFlaw = useCallback(
    (n: Flaw) =>
      setFilters((f) =>
        f.flaws.includes(n)
          ? { ...f, flaws: f.flaws.filter((x) => x !== n) }
          : { ...f, flaws: [...f.flaws, n], needs: f.needs.filter((x) => x !== n) },
      ),
    [],
  );
  const clear = useCallback(
    () => setFilters((f) => ({ ...f, topic: "", cuisine: "", borough: "", needs: [], flaws: [] })),
    [],
  );

  return { filters, update, toggleNeed, toggleFlaw, clear };
}
