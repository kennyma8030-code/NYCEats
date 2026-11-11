/**
 * The city the page is showing, as its subreddit: ?subreddit=FoodLosAngeles.
 *
 * It is read once, when the page loads, and every API request carries it
 * (api/client.ts). Changing city loads the page again at the new URL rather
 * than updating in place: everything on screen and every cache (the name
 * list, the per-restaurant memo, an open restaurant) belongs to one city, and
 * a place's key means something else in the next one.
 *
 * state/filters.ts rebuilds the query string as filters change and carries
 * this parameter over by name.
 *
 * No parameter means r/FoodNYC, which is what the API means by it too, so
 * every link from before there was a second city still opens New York.
 */
export const HOME = "FoodNYC";

const PARAM = "subreddit";

export function cityFromQuery(search: string): string {
  return new URLSearchParams(search).get(PARAM)?.trim() || HOME;
}

export const SUBREDDIT: string = typeof window === "undefined" ? HOME : cityFromQuery(window.location.search);

/** An API path with the city on it. New York's is left bare, as the API reads it. */
export function withCity(path: string, subreddit: string = SUBREDDIT): string {
  if (subreddit === HOME) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${PARAM}=${encodeURIComponent(subreddit)}`;
}

/** Where the page for another city lives. Filters and the open restaurant are
 *  left behind: a cuisine, an area or a key from one city names nothing in another. */
export function cityUrl(subreddit: string, pathname: string): string {
  return subreddit === HOME ? pathname : `${pathname}?${PARAM}=${encodeURIComponent(subreddit)}`;
}

/** What the parts of a city are called: New York has boroughs, the other
 *  cities' lists give the cities and districts their places are in. */
export function areaWords(subreddit: string = SUBREDDIT): { one: string; all: string } {
  return subreddit === HOME ? { one: "Borough", all: "All boroughs" } : { one: "Area", all: "All areas" };
}
