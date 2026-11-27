// Where the app is, as a query string, and the rules for moving between
// places in it. Pure and free of React so the rules can be tested on their
// own (frontend/tests); hooks/useRoute.ts is the part that touches history.
import type { Flaw, Need, WindowDays } from "../api/types";
import { HOME } from "./city.ts";
import { FLAWS, NEEDS, filtersFromQuery, isWindow, type Filters } from "./filters.ts";

/** The three rankings. Each is one axis; there is no combined score.
 *  loved and gems are rating boards (/api/boards), talked is a count over a
 *  period (/api/ledger). */
export type SortId = "loved" | "talked" | "gems";

export interface Route {
  /** home is the landing page and the list of cities; city is the map. */
  screen: "home" | "city";
  /** The city's subreddit. On the home screen it is New York, which nothing shows. */
  city: string;
  sort: SortId;
  /** The period the counts cover; null is the sort's own (SORTS[].window). */
  window: WindowDays | null;
  topic: string;
  /** A typed search (/api/search). While there is one the panel lists its
   *  answer in place of the ranking, which the sort and filters belong to. */
  q: string;
  cuisine: string;
  borough: string;
  needs: Need[];
  flaws: Flaw[];
  /** The open restaurant's key. */
  place: string | null;
  /** ?dev=1 shows the per-comment extraction link. */
  dev: boolean;
}

export const SORT_IDS: SortId[] = ["loved", "talked", "gems"];
export const DEFAULT_SORT: SortId = "loved";

/** Whether the ledger answers this sort, and so whether a topic, a "good
 *  for" or a complaint can filter it. The rating boards take only a cuisine
 *  and an area. */
export const isLedgerSort = (s: SortId) => s === "talked";

export const HOME_ROUTE: Route = {
  screen: "home", city: HOME, sort: DEFAULT_SORT, window: null, topic: "", q: "", cuisine: "", borough: "",
  needs: [], flaws: [], place: null, dev: false,
};

// Links from the old interface: ?category= named a ledger list and
// ?view=boards&board= a rating board. A link to Trending, which is gone,
// names no list and opens the city on its usual one, over that list's usual
// period: the week in the link was Trending's.
const namesTrending = (p: URLSearchParams) => p.get("sort") === "trending" || p.get("category") === "trending";

function legacySort(p: URLSearchParams): SortId | null {
  if (p.get("view") === "boards") return p.get("board") === "gems" ? "gems" : "loved";
  const c = p.get("category");
  return c === "top" ? "talked" : c === "gems" ? "gems" : null;
}

// Any of these in a link means a city is open. A bare URL is the landing page.
const CITY_PARAMS = ["subreddit", "r", "sort", "topic", "q", "cuisine", "borough", "need", "flaw", "window", "category", "view"];

export function parseRoute(search: string): Route {
  const p = new URLSearchParams(search);
  const dev = p.get("dev") === "1";
  if (!CITY_PARAMS.some((k) => p.has(k))) return { ...HOME_ROUTE, dev };
  const f = filtersFromQuery(search, null);
  const named = p.get("sort");
  // Only a sort the link names outright can outrank its filters (settle).
  const asked = SORT_IDS.includes(named as SortId) ? (named as SortId) : legacySort(p);
  const win = Number(p.get("window"));
  return settle({
    screen: "city",
    city: p.get("subreddit")?.trim() || HOME,
    sort: asked ?? DEFAULT_SORT,
    window: isWindow(win) && !namesTrending(p) ? win : null,
    topic: f.topic.trim(),
    q: (p.get("q") ?? "").trim(),
    cuisine: f.cuisine,
    borough: f.borough,
    needs: f.needs,
    flaws: f.flaws,
    place: p.get("r") || null,
    dev,
  }, asked);
}

/** The query string for a route, "" for the bare landing page. A city always
 *  names its subreddit, New York included, because that is what tells a city
 *  link from the landing page. */
export function formatRoute(r: Route): string {
  const p = new URLSearchParams();
  if (r.screen === "city") {
    p.set("subreddit", r.city);
    if (r.sort !== DEFAULT_SORT) p.set("sort", r.sort);
    if (r.window != null) p.set("window", String(r.window));
    if (r.topic) p.set("topic", r.topic);
    if (r.q) p.set("q", r.q);
    if (r.cuisine) p.set("cuisine", r.cuisine);
    if (r.borough) p.set("borough", r.borough);
    r.needs.forEach((n) => p.append("need", n));
    r.flaws.forEach((n) => p.append("flaw", n));
    if (r.place) p.set("r", r.place);
  }
  if (r.dev) p.set("dev", "1");
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

const LEDGER_ONLY = (r: Route) => r.topic !== "" || r.needs.length > 0 || r.flaws.length > 0;

// A sort and its filters have to agree, because the rating boards cannot
// filter by topic, "good for" or complaint. `keep` is the side the person
// just chose: picking a board drops the filters it cannot apply, and
// anything else moves a board to the list that can.
function settle(r: Route, keep: SortId | null): Route {
  if (isLedgerSort(r.sort) || !LEDGER_ONLY(r)) return r;
  if (keep != null && !isLedgerSort(keep)) return { ...r, topic: "", needs: [], flaws: [] };
  return { ...r, sort: "talked" };
}

const RANKING_KEYS = ["sort", "window", "topic", "cuisine", "borough", "needs", "flaws"] as const;

/** The route after a change. Changing city starts that city clean: a
 *  cuisine, an area or a key from one city names nothing in another. An
 *  aspect cannot be both wanted and complained of (the API refuses the
 *  pair), so the one just ticked wins. */
export function applyPatch(r: Route, patch: Partial<Route>): Route {
  if (patch.screen === "home") return { ...HOME_ROUTE, dev: r.dev };
  if (patch.city != null && (patch.city !== r.city || r.screen === "home")) {
    return settle({ ...HOME_ROUTE, dev: r.dev, ...patch, screen: "city" }, patch.sort ?? null);
  }
  let next: Route = { ...r, ...patch, screen: "city" };
  if (patch.needs) next = { ...next, flaws: next.flaws.filter((x) => !(patch.needs as string[]).includes(x)) };
  else if (patch.flaws) next = { ...next, needs: next.needs.filter((x) => !(patch.flaws as string[]).includes(x)) };
  next = { ...next, topic: next.topic.trim(), q: next.q.trim() };
  // A sort or a filter is asked of the ranking, so choosing one leaves the
  // search. Opening and closing a restaurant does not.
  if (patch.q === undefined && RANKING_KEYS.some((k) => patch[k] !== undefined)) next = { ...next, q: "" };
  // A new sort has its own usual period, not the one chosen for the last.
  if (patch.sort != null && patch.sort !== r.sort && patch.window === undefined) next = { ...next, window: null };
  return settle(next, patch.sort ?? null);
}

export const toggle = <T,>(xs: T[], x: T): T[] => (xs.includes(x) ? xs.filter((y) => y !== x) : [...xs, x]);

export const filterCount = (r: Route) =>
  (r.topic ? 1 : 0) + (r.cuisine ? 1 : 0) + (r.borough ? 1 : 0) + r.needs.length + r.flaws.length;

/** The ledger's own filter object for a ledger sort over `window`. */
export function ledgerFilters(r: Route, window: WindowDays): Filters {
  return {
    algo: "v1", topic: r.topic, category: "top", window,
    cuisine: r.cuisine, borough: r.borough, needs: r.needs, flaws: r.flaws,
  };
}

export const needLabel = (k: Need) => NEEDS.find((n) => n.k === k)?.label ?? k;
export const flawLabel = (k: Flaw) => FLAWS.find((n) => n.k === k)?.label ?? k;
