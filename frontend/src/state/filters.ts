import { useCallback, useEffect, useState } from "react";
import type { Category, Need, WindowDays } from "../api/types";

export interface Filters {
  category: Category;
  window: WindowDays;
  cuisine: string;
  borough: string;
  needs: Need[];
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

export const DEFAULT_FILTERS: Filters = { category: "trending", window: 7, cuisine: "", borough: "", needs: [] };

export const windowOf = (d: WindowDays) => WINDOWS.find((w) => w.d === d) ?? WINDOWS[0];
export const categoryOf = (k: Category) => CATEGORIES.find((c) => c.k === k) ?? CATEGORIES[0];

// The URL is the source of truth on load, so a filtered view can be shared.
function fromUrl(): Filters {
  const p = new URLSearchParams(window.location.search);
  const cat = p.get("category");
  const win = Number(p.get("window"));
  return {
    category: CATEGORIES.some((c) => c.k === cat) ? (cat as Category) : DEFAULT_FILTERS.category,
    window: WINDOWS.some((w) => w.d === win) ? (win as WindowDays) : DEFAULT_FILTERS.window,
    cuisine: p.get("cuisine") ?? "",
    borough: p.get("borough") ?? "",
    needs: p.getAll("need").filter((n): n is Need => NEEDS.some((x) => x.k === n)),
  };
}

function toUrl(f: Filters) {
  const p = new URLSearchParams();
  if (f.category !== DEFAULT_FILTERS.category) p.set("category", f.category);
  if (f.window !== DEFAULT_FILTERS.window) p.set("window", String(f.window));
  if (f.cuisine) p.set("cuisine", f.cuisine);
  if (f.borough) p.set("borough", f.borough);
  f.needs.forEach((n) => p.append("need", n));
  const qs = p.toString();
  window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

export function activeFilterCount(f: Filters) {
  return (f.cuisine ? 1 : 0) + (f.borough ? 1 : 0) + f.needs.length;
}

export function useFilters() {
  const [filters, setFilters] = useState<Filters>(fromUrl);
  useEffect(() => toUrl(filters), [filters]);

  const update = useCallback((patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch })), []);
  const toggleNeed = useCallback(
    (n: Need) =>
      setFilters((f) => ({ ...f, needs: f.needs.includes(n) ? f.needs.filter((x) => x !== n) : [...f.needs, n] })),
    [],
  );
  const clear = useCallback(() => setFilters((f) => ({ ...f, cuisine: "", borough: "", needs: [] })), []);

  return { filters, update, toggleNeed, clear };
}
