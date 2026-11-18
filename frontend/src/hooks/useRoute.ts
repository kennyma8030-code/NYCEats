import { useCallback, useEffect, useRef, useState } from "react";
import { applyPatch, formatRoute, parseRoute, type Route } from "../state/route";

/**
 * The route, kept in the URL so any view can be shared or reloaded.
 *
 * Going somewhere (into a city, onto a restaurant, back out) adds a history
 * entry, so the browser's Back button does what the panel's own back buttons
 * do. Adjusting where you are (a sort, a filter) replaces the entry, so Back
 * does not have to be pressed once per chip.
 */
export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.search));
  // The latest route, so two changes in one tick build on each other.
  const latest = useRef(route);

  useEffect(() => {
    const onPop = () => {
      latest.current = parseRoute(window.location.search);
      setRoute(latest.current);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const go = useCallback((patch: Partial<Route>) => {
    const from = latest.current;
    const next = applyPatch(from, patch);
    latest.current = next;
    const url = formatRoute(next) || window.location.pathname;
    const moved = next.screen !== from.screen || next.city !== from.city || next.place !== from.place;
    if (moved) window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
    setRoute(next);
  }, []);

  return { route, go };
}
