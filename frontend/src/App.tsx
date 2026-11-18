import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api } from "./api/client";
import type { LedgerItem } from "./api/types";
import { BRAND_NAME } from "./brand";
import { Leaderboard } from "./components/city/Leaderboard";
import { Home } from "./components/home/Home";
import { MapCredit } from "./components/MapCredit";
import { PlacePanels } from "./components/place/Place";
import type { Scope } from "./components/Search";
import { useCities } from "./hooks/useCities";
import { useFacets } from "./hooks/useFacets";
import { useFetch } from "./hooks/useFetch";
import { useHoverPreview } from "./hooks/useHoverPreview";
import { useRanking } from "./hooks/useRanking";
import { useRestaurant } from "./hooks/useRestaurant";
import { useRoute } from "./hooks/useRoute";
import { useViewport } from "./hooks/useViewport";
import { cityView, pinBounds } from "./lib/cities";
import { cityLayout, mapSides } from "./lib/layout";
import { isRankable } from "./lib/rating";
import { rowMetric } from "./lib/sorts";
import type { MapPadding, MapPin, MapTarget } from "./map/MapView";
import { HOME, setCurrentCity } from "./state/city";
import "./components/city/City.css";

// MapLibre is most of the bundle and nothing on the first screen needs it,
// so it arrives after the title and search have been drawn.
const MapView = lazy(() => import("./map/MapView"));

const SHEET = 0.62;       // of the height, on a phone
const SHEET_PEEK = 132;   // px, when the sheet is folded down to see the map
const PLACE_ZOOM = 15.2;

const NO_PINS: MapPin[] = [];
const NO_DOTS: { lat: number; lng: number }[] = [];

/**
 * One map for the whole app, fixed behind everything, and two things drawn
 * over it: the landing page (which scrolls, and covers the map with its
 * first screen) and a city's panels: the list, the restaurant beside it,
 * and that restaurant's comments. Moving between them, and onto a
 * restaurant, moves the map's camera rather than swapping one map for
 * another.
 */
export default function App() {
  const { route, go } = useRoute();
  // Set while rendering, before any child asks the API for anything: every
  // request made below is this city's (state/city.ts).
  setCurrentCity(route.city);
  const inCity = route.screen === "city";
  const view = useViewport();

  const cities = useCities();
  // The city highlighted on the landing page, which the map behind it shows.
  const [preview, setPreview] = useState(HOME);
  const previewTop = useFetch(inCity ? null : `top|${preview}`, () => api.cityTop(preview));

  const facets = useFacets(inCity ? route.city : null);
  const ranking = useRanking(route, inCity);
  const [hot, setHot] = useState<string | null>(null);
  const [peek, setPeek] = useState(false);

  // ---- The open restaurant, as a list row: the list's own when it is on
  // the list, otherwise fetched alone (a searched place, a shared link). ----
  const key = inCity ? route.place : null;
  const index = key ? ranking.items.findIndex((i) => i.entity_key === key) : -1;
  const listed = index >= 0 ? ranking.items[index] : null;
  const lone = useFetch(
    key && !listed ? `${route.city}|${key}|${ranking.window}|${route.topic}` : null,
    () => api.ledgerEntity(key as string, ranking.window, route.topic),
  );
  const loneItem = lone.current && lone.data?.entity_key === key ? lone.data : null;
  // Kept while the same place is open, so a list reloading under it does not blank the panel.
  const kept = useRef<LedgerItem | null>(null);
  const found = listed ?? loneItem;
  if (found) kept.current = found;
  else if (kept.current?.entity_key !== key) kept.current = null;
  const item = key ? kept.current : null;
  const detail = useRestaurant(key);

  // ---- The row the pointer is resting on, previewed beside the list. It
  // only ever highlights that row's pin: the map does not move for a hover. ----
  const { shown, hover } = useHoverPreview(inCity && !key && !view.phone);
  const previewed = shown ? ranking.items.find((i) => i.entity_key === shown.key) ?? null : null;
  // The panels' widths (lib/layout.ts). The map is padded for the panels
  // that stay put, so a preview coming and going does not shift it.
  const layout = useMemo(
    () => cityLayout(view.width, key ? "open" : previewed ? "preview" : "list"),
    [view.width, key, previewed],
  );
  const sides = useMemo(() => mapSides(view.width, cityLayout(view.width, key ? "open" : "list")), [view.width, key]);

  const scope: Scope = useMemo(() => {
    const c = cities.data?.find((x) => x.subreddit === route.city);
    return { subreddit: route.city, name: c?.name ?? `r/${route.city}`, short: c?.short ?? route.city };
  }, [cities.data, route.city]);

  // ---- What the map shows ----
  const pins: MapPin[] = useMemo(() => {
    if (!inCity) {
      if (!previewTop.current || !previewTop.data) return NO_PINS;
      return previewTop.data.items.filter((i) => isRankable(i.rating)).flatMap((i, n) =>
        i.location ? [{ key: i.entity_key, rank: n + 1, name: i.name, lat: i.location.lat, lng: i.location.lng, label: `${n + 1}. ${i.name}` }] : []);
    }
    const out: MapPin[] = ranking.items.flatMap((i, n) => {
      if (!i.location) return [];
      const m = rowMetric(route.sort, i);
      return [{ key: i.entity_key, rank: n + 1, name: i.name, lat: i.location.lat, lng: i.location.lng, label: `${n + 1}. ${i.name}, ${m.big} ${m.small}` }];
    });
    // A place opened from search is not on the list, but is still somewhere.
    if (item?.location && !listed) {
      out.push({ key: item.entity_key, rank: null, name: item.name, lat: item.location.lat, lng: item.location.lng, label: item.name });
    }
    return out;
  }, [inCity, previewTop.current, previewTop.data, ranking.items, route.sort, item, listed]);

  const dots = useMemo(
    () => (key && detail.data?.locations && detail.data.locations.length > 1 ? detail.data.locations.slice(1) : NO_DOTS),
    [key, detail.data],
  );

  const target: MapTarget = useMemo(() => {
    if (!inCity) {
      const v = cityView(preview);
      return { id: `home|${preview}`, center: v.center, zoom: v.zoom - (view.phone ? 0.8 : 0.3) };
    }
    if (key) {
      const at = item?.location;
      // No coordinates (or not known yet): hold the map where it is.
      return at ? { id: `place|${route.city}|${key}`, center: [at.lng, at.lat], zoom: PLACE_ZOOM } : { id: `place|${route.city}|${key}|` };
    }
    const placed = ranking.items.flatMap((i) => (i.location ? [i.location] : []));
    const bounds = pinBounds(placed);
    // Named by the rows it frames, so the map refits when the list changes and not before.
    if (bounds) return { id: `list|${route.city}|${ranking.items.map((i) => i.entity_key).join("\n")}`, bounds, maxZoom: 13.5 };
    return { id: `city|${route.city}`, ...cityView(route.city) };
  }, [inCity, preview, view.phone, key, item, route.city, ranking.items]);

  const padding: MapPadding = useMemo(() => {
    if (!inCity) {
      return view.phone
        ? { top: 80, right: 20, bottom: 40, left: 20 }
        : { top: 140, right: 40, bottom: 60, left: Math.round(view.width * 0.38) };
    }
    return view.phone
      ? { top: 56, right: 28, bottom: (peek ? SHEET_PEEK : Math.round(view.height * SHEET)) + 16, left: 28 }
      : { top: 48, right: sides.right, bottom: 48, left: sides.left };
  }, [inCity, view.phone, view.width, view.height, peek, sides]);

  // ---- Moving about ----
  const openPlace = useCallback((place: string) => {
    setHot(null);
    setPeek(false);
    // In the same update as the route, so the preview's panel is the one
    // that grows into the restaurant rather than a new one replacing it.
    hover.cancel();
    go({ place });
  }, [go, hover]);
  const closePlace = useCallback(() => {
    const was = route.place;
    go({ place: null });
    // Back to the row it was opened from, for whoever is using the keyboard.
    if (was) requestAnimationFrame(() => document.querySelector<HTMLElement>(`.row[data-key="${CSS.escape(was)}"]`)?.focus({ preventScroll: true }));
  }, [go, route.place]);
  const openCity = useCallback((city: string) => go({ city }), [go]);
  const pickPin = useCallback((place: string) => {
    if (inCity) openPlace(place);
    else go({ city: preview, place });
  }, [inCity, openPlace, go, preview]);

  useEffect(() => {
    setHot(null);
    hover.cancel();
  }, [route.city, route.sort, route.screen, hover]);

  useEffect(() => {
    const here = [inCity && item && key ? item.name : null, inCity ? scope.name : null].filter(Boolean).join(", ");
    document.title = here ? `${here} | ${BRAND_NAME}` : BRAND_NAME;
  }, [inCity, item, key, scope.name]);

  const grab = view.phone && (
    <button
      type="button" className="panel-grab" aria-expanded={!peek}
      aria-label={peek ? "Show the list" : "Show more of the map"} onClick={() => setPeek((p) => !p)}
    />
  );
  const lit = hot ?? previewed?.entity_key ?? null;
  const widths = { "--board": `${layout.board}px`, "--place": `${layout.place}px`, "--comments": `${layout.comments}px` } as CSSProperties;

  return (
    <>
      <div className="map-stage">
        <Suspense fallback={null}>
          <MapView
            target={target} padding={padding} pins={pins} dots={dots} hot={lit} selected={key} live={inCity}
            onHot={setHot} onPick={pickPin}
          />
        </Suspense>
      </div>

      <Home
        cities={cities.data} citiesError={cities.error} active={preview} top={previewTop} onActive={setPreview}
        onOpen={openCity} onPlace={(city, place) => go({ city, place })} onTopic={(city, topic) => go({ city, topic })}
        hidden={inCity}
      />

      {inCity && (
        <div className="city" style={widths}>
          {/* A phone has room for one panel: the restaurant takes the list's place. */}
          {!(view.phone && key) && (
            <aside className={`panel board-panel${key ? " strip" : ""}${peek ? " peek" : ""}`} aria-label={scope.name}>
              {grab}
              <Leaderboard
                route={route} go={go} scope={scope} facets={facets.current ? facets.data : null} ranking={ranking}
                hot={lit} onHot={setHot} onOpen={openPlace} selected={key} hover={hover}
              />
            </aside>
          )}
          {key ? (
            <PlacePanels
              mode="open" entityKey={key} item={item} error={!item ? lone.error : null} columns={layout.columns}
              rowTop={0} viewportHeight={view.height} grab={grab} peek={peek} dev={route.dev}
              onOpen={() => openPlace(key)} onClose={closePlace} onHold={hover.hold} onRelease={hover.leave}
            />
          ) : previewed && shown && (
            <PlacePanels
              mode="preview" entityKey={previewed.entity_key} item={previewed} error={null} columns={false}
              rowTop={shown.top} viewportHeight={view.height} dev={route.dev}
              onOpen={() => openPlace(previewed.entity_key)} onClose={hover.cancel} onHold={hover.hold} onRelease={hover.leave}
            />
          )}
          <MapCredit />
        </div>
      )}
    </>
  );
}
