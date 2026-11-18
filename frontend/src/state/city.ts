/**
 * The city on screen, as its subreddit: ?subreddit=FoodLosAngeles.
 *
 * Every API request is one city's, so the client puts the city on each one
 * (api/client.ts) from here rather than trusting every caller to pass it.
 * The city changes without a page load now, so it is a value the route sets
 * (state/route.ts) and not a constant: whatever caches by city keys on it,
 * because a place's key means something else in the next one.
 *
 * A request with no subreddit means r/FoodNYC, which is what the API means
 * by it too, so New York's paths stay as they were before there was a
 * second city.
 */
export const HOME = "FoodNYC";

const PARAM = "subreddit";

/** The city a query string names; New York when it names none. */
export function cityFromQuery(search: string): string {
  return new URLSearchParams(search).get(PARAM)?.trim() || HOME;
}

let current: string = HOME;

export const currentCity = (): string => current;

export function setCurrentCity(subreddit: string): void {
  current = subreddit;
}

/** An API path with the city on it. New York's is left bare, as the API reads it. */
export function withCity(path: string, subreddit: string = current): string {
  if (subreddit === HOME) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${PARAM}=${encodeURIComponent(subreddit)}`;
}

/** What the parts of a city are called: New York has boroughs, the other
 *  cities' lists give the cities and districts their places are in. */
export function areaWords(subreddit: string = current): { one: string; all: string } {
  return subreddit === HOME ? { one: "Borough", all: "All boroughs" } : { one: "Area", all: "All areas" };
}
