import { useEffect, useRef } from "react";
import { Map as MapLibre, Marker, NavigationControl, setWorkerUrl } from "maplibre-gl";
// MapLibre finds its worker beside its own file, which a bundle no longer
// is; asking Vite for the worker's URL keeps the two together in dev and in
// the build.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { fontRequest, mapStyle } from "./style";
import "./map.css";

setWorkerUrl(workerUrl);

/** The classic teardrop, solid, with its tip on the bottom edge of the
 *  button: the marker is anchored there, so the tip is the coordinate. */
const PIN_SVG =
  '<svg class="pin-shape" width="28" height="36" viewBox="0 0 28 36" aria-hidden="true">' +
  '<path d="M14 34.5C14 34.5 1.5 22 1.5 13.5a12.5 12.5 0 0 1 25 0C26.5 22 14 34.5 14 34.5z"/></svg>';

/** A place on the map, drawn as a pin. `rank` is its place in the list beside
 *  it and only decides which pin lies on top where two overlap; null is an
 *  open place the list does not hold, which lies beneath the ranked ones. */
export interface MapPin {
  key: string;
  rank: number | null;
  name: string;
  lat: number;
  lng: number;
  /** What a screen reader says for it: the row's own words. */
  label: string;
}

/** Where the camera should be. `id` names the view: the map moves when it
 *  changes and holds still while it does not, however often it re-renders. */
export interface MapTarget {
  id: string;
  center?: [number, number];
  zoom?: number;
  /** [[west, south], [east, north]] to fit instead of a centre. */
  bounds?: [[number, number], [number, number]];
  maxZoom?: number;
}

export interface MapPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

interface Props {
  target: MapTarget;
  /** The part of the map covered by the panel, so nothing is centred under it. */
  padding: MapPadding;
  pins: MapPin[];
  /** Further locations of the open place, drawn small and without a number. */
  dots: { lat: number; lng: number }[];
  hot: string | null;
  selected: string | null;
  /** False on the landing page, where the map is a backdrop. */
  live: boolean;
  onHot: (key: string | null) => void;
  onPick: (key: string) => void;
}

interface Drawn {
  marker: Marker;
  el: HTMLButtonElement;
  tag: HTMLSpanElement;
}

// A move inside a city is a second, like the panel's own transitions; one
// between cities crosses a continent and gets longer to do it.
const NEAR_MS = 1100;
const FAR_MS = 2400;

export default function MapView({ target, padding, pins, dots, hot, selected, live, onHot, onPick }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibre | null>(null);
  const drawn = useRef(new Map<string, Drawn>());
  const minor = useRef<Marker[]>([]);
  const moved = useRef<string | null>(null);
  // The handlers the markers call: always the latest, without rebuilding a marker.
  const handlers = useRef({ onHot, onPick });
  handlers.current = { onHot, onPick };
  const first = useRef({ target, padding });

  useEffect(() => {
    if (!box.current) return;
    const t = first.current.target;
    const m = new MapLibre({
      container: box.current,
      style: mapStyle(),
      center: t.center ?? [-96, 39],
      zoom: t.zoom ?? 3.4,
      minZoom: 2.5,
      maxZoom: 18,
      // The credit is drawn by the app (MapCredit), where no panel covers it.
      attributionControl: false,
      // North stays up and the map stays flat: the pins are read against the
      // list, and a tilted or turned map makes that harder for nothing.
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      transformRequest: (url) => fontRequest(url),
    });
    m.touchZoomRotate.disableRotation();
    m.keyboard.disableRotation();
    m.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    map.current = m;
    const markers = drawn.current;
    return () => {
      m.remove();
      map.current = null;
      markers.clear();
      minor.current = [];
      moved.current = null;
    };
  }, []);

  // Move when the view named by target.id changes. The first view is set
  // without an animation: there is nowhere to arrive from.
  useEffect(() => {
    const m = map.current;
    if (!m || moved.current === target.id) return;
    const start = moved.current === null;
    moved.current = target.id;
    if (target.bounds) {
      m.fitBounds(target.bounds, { padding, maxZoom: target.maxZoom ?? 14, duration: start ? 0 : NEAR_MS });
      return;
    }
    if (!target.center) {
      // Nowhere new to go (a place with no coordinates): only make room for the panel.
      m.easeTo({ padding, duration: start ? 0 : NEAR_MS });
      return;
    }
    const here = m.getCenter();
    const far = Math.abs(here.lng - target.center[0]) + Math.abs(here.lat - target.center[1]) > 1.5;
    const to = { center: target.center, zoom: target.zoom ?? m.getZoom(), padding };
    if (start) m.jumpTo(to);
    else m.flyTo({ ...to, duration: far ? FAR_MS : NEAR_MS, curve: far ? 1.3 : 1.1 });
  }, [target, padding]);

  // The pins are the list's rows, by key: ones that stay are moved and
  // reordered in place, so a pin under the pointer survives a new sort.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const markers = drawn.current;
    const wanted = new Set(pins.map((p) => p.key));
    for (const [key, d] of markers) {
      if (!wanted.has(key)) {
        d.marker.remove();
        markers.delete(key);
      }
    }
    for (const p of pins) {
      let d = markers.get(p.key);
      if (!d) {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "pin";
        el.innerHTML = PIN_SVG;
        const tag = document.createElement("span");
        tag.className = "pin-tag";
        el.append(tag);
        const key = p.key;
        el.addEventListener("mouseenter", () => handlers.current.onHot(key));
        el.addEventListener("mouseleave", () => handlers.current.onHot(null));
        el.addEventListener("focus", () => handlers.current.onHot(key));
        el.addEventListener("blur", () => handlers.current.onHot(null));
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          handlers.current.onPick(key);
        });
        d = { el, tag, marker: new Marker({ element: el, anchor: "bottom" }).setLngLat([p.lng, p.lat]).addTo(m) };
        markers.set(key, d);
      } else {
        d.marker.setLngLat([p.lng, p.lat]);
      }
      d.tag.textContent = p.name;
      d.el.setAttribute("aria-label", p.label);
      // The best-ranked pin wins where two overlap.
      d.el.style.zIndex = String(100 - (p.rank ?? 0));
    }
  }, [pins]);

  useEffect(() => {
    for (const [key, d] of drawn.current) d.el.classList.toggle("on", key === hot || key === selected);
  }, [pins, hot, selected]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    minor.current.forEach((x) => x.remove());
    minor.current = dots.map((p) => {
      const el = document.createElement("span");
      el.className = "pin-minor";
      el.setAttribute("aria-hidden", "true");
      return new Marker({ element: el }).setLngLat([p.lng, p.lat]).addTo(m);
    });
  }, [dots]);

  return <div ref={box} className={live ? "map live" : "map"} aria-label="Map" />;
}
