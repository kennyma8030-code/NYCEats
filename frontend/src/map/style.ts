// The map's style, written by hand for this app rather than taken from a
// stock one: flat land, water and parks, thin faint lines for the roads that
// give a city its shape, and the names of its neighbourhoods. No buildings,
// no shop or station icons, no highway shields. The restaurants are the only
// things on it that ask to be looked at.
//
// Tiles are OpenFreeMap's public vector tiles (the OpenMapTiles schema),
// which need no key.
import type { MapOptions } from "maplibre-gl";
import latin500 from "@fontsource/inter/files/inter-latin-500-normal.woff2";
import latinExt500 from "@fontsource/inter/files/inter-latin-ext-500-normal.woff2";
import latin600 from "@fontsource/inter/files/inter-latin-600-normal.woff2";
import latinExt600 from "@fontsource/inter/files/inter-latin-ext-600-normal.woff2";

type Style = Exclude<NonNullable<MapOptions["style"]>, string>;
type Layer = Style["layers"][number];

const TILES = "https://tiles.openfreemap.org/planet";
const FONTS = "https://tiles.openfreemap.org/fonts/";
const FALLBACK_FONT = "Noto Sans Regular";

export const ATTRIBUTION: { label: string; href: string }[] = [
  { label: "OpenFreeMap", href: "https://openfreemap.org" },
  { label: "© OpenMapTiles", href: "https://www.openmaptiles.org/" },
  { label: "© OpenStreetMap", href: "https://www.openstreetmap.org/copyright" },
];

/** The tile server has no Inter, so the labels are drawn in the browser from
 *  the same Inter files the package ships (the style's `font-faces`). A
 *  character those files lack falls back to the glyph server, which is asked
 *  for a stack it does not have; this sends that request to one it does. */
export function fontRequest(url: string): { url: string } | undefined {
  if (!url.startsWith(FONTS)) return undefined;
  return { url: url.replace(/^(.*\/fonts\/)[^/]+\//, `$1${encodeURIComponent(FALLBACK_FONT)}/`) };
}

// The Latin Extended block as Google Fonts cuts it; the plain Latin file is
// listed after it without a range, so it answers for everything else.
const LATIN_EXT = [
  "U+0100-02BA", "U+02BD-02C5", "U+02C7-02CC", "U+02CE-02D7", "U+02DD-02FF", "U+0304", "U+0308", "U+0329",
  "U+1D00-1DBF", "U+1E00-1E9F", "U+1EF2-1EFF", "U+2020", "U+20A0-20AB", "U+20AD-20C0", "U+2113", "U+2C60-2C7F",
  "U+A720-A7FF",
];

const absolute = (path: string) => new URL(path, window.location.href).href;
const face = (ext: string, latin: string) => [
  { url: absolute(ext), "unicode-range": LATIN_EXT },
  { url: absolute(latin) },
];

const token = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

const NAME = ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]];
const classIn = (...classes: string[]) => ["match", ["get", "class"], classes, true, false];
const grow = (...stops: number[]) => ["interpolate", ["exponential", 1.6], ["zoom"], ...stops];

export function mapStyle(): Style {
  // Read from styles/tokens.css, so the map and the page share one palette.
  const water = token("--map-water", "#151B22");
  const land = token("--map-land", "#23262B");
  const land2 = token("--map-land-2", "#2A2E34");
  const park = token("--map-park", "#26332B");
  const waterInk = token("--map-water-ink", "#7F97AA");
  const label = token("--map-label", "#9A9CA1");
  const ink = token("--map-ink", "#E6E4DE");
  const roadRgb = token("--map-road", "255, 255, 255");
  const halo = { "text-halo-color": land, "text-halo-width": 1.4 };

  const road = (id: string, classes: string[], minzoom: number, alpha: number, widths: number[]) => ({
    id, type: "line", source: "omt", "source-layer": "transportation", minzoom,
    // Tunnels are left out: a road nobody can see from the street is not part of the shape.
    filter: ["all", ["==", ["geometry-type"], "LineString"], classIn(...classes), ["!=", ["get", "brunnel"], "tunnel"]],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": `rgba(${roadRgb}, ${alpha})`, "line-width": grow(...widths) },
  });

  const layers = [
    { id: "land", type: "background", paint: { "background-color": land } },
    {
      id: "built", type: "fill", source: "omt", "source-layer": "landuse",
      filter: classIn("industrial", "commercial", "retail", "railway", "military", "quarry"),
      paint: { "fill-color": land2 },
    },
    {
      id: "green", type: "fill", source: "omt", "source-layer": "landcover",
      filter: classIn("grass", "wood"),
      paint: { "fill-color": park, "fill-opacity": 0.7 },
    },
    {
      id: "green-use", type: "fill", source: "omt", "source-layer": "landuse",
      filter: classIn("cemetery", "pitch", "playground", "stadium"),
      paint: { "fill-color": park, "fill-opacity": 0.7 },
    },
    { id: "park", type: "fill", source: "omt", "source-layer": "park", paint: { "fill-color": park } },
    {
      id: "runway", type: "line", source: "omt", "source-layer": "aeroway", minzoom: 11,
      filter: ["all", ["==", ["geometry-type"], "LineString"], classIn("runway")],
      paint: { "line-color": land2, "line-width": grow(11, 2, 16, 40) },
    },
    { id: "water", type: "fill", source: "omt", "source-layer": "water", paint: { "fill-color": water } },
    {
      id: "waterway", type: "line", source: "omt", "source-layer": "waterway", minzoom: 9,
      paint: { "line-color": water, "line-width": grow(9, 0.6, 16, 5) },
    },

    // Major roads from far out; lesser ones only as the reader zooms in.
    road("road-minor", ["minor"], 13.5, 0.07, [13.5, 0.4, 16, 1.6, 19, 10]),
    road("road-mid", ["secondary", "tertiary"], 11.5, 0.09, [11.5, 0.5, 14, 1.2, 19, 14]),
    road("road-major", ["motorway", "trunk", "primary"], 6, 0.14, [6, 0.4, 11, 0.9, 14, 2, 19, 18]),

    {
      id: "street-name", type: "symbol", source: "omt", "source-layer": "transportation_name", minzoom: 15,
      // Streets only: the layer also names ferry routes and rail lines.
      filter: classIn("motorway", "trunk", "primary", "secondary", "tertiary", "minor"),
      layout: {
        "symbol-placement": "line", "text-field": NAME, "text-font": ["Inter Medium"], "text-size": 11,
        "text-max-angle": 30, "symbol-spacing": 420,
      },
      paint: { "text-color": label, ...halo },
    },
    {
      id: "water-name", type: "symbol", source: "omt", "source-layer": "water_name", minzoom: 8,
      filter: ["==", ["geometry-type"], "Point"],
      layout: {
        "text-field": NAME, "text-font": ["Inter Medium"], "text-size": 12, "text-letter-spacing": 0.18, "text-max-width": 6,
      },
      paint: { "text-color": waterInk, "text-halo-color": water, "text-halo-width": 1 },
    },
    {
      id: "river-name", type: "symbol", source: "omt", "source-layer": "water_name", minzoom: 10,
      filter: ["==", ["geometry-type"], "LineString"],
      layout: {
        "symbol-placement": "line", "text-field": NAME, "text-font": ["Inter Medium"], "text-size": 12,
        "text-letter-spacing": 0.18, "symbol-spacing": 500,
      },
      paint: { "text-color": waterInk, "text-halo-color": water, "text-halo-width": 1 },
    },
    {
      id: "neighbourhood", type: "symbol", source: "omt", "source-layer": "place", minzoom: 11,
      filter: classIn("suburb", "quarter", "neighbourhood", "borough"),
      layout: {
        "text-field": NAME, "text-font": ["Inter SemiBold"], "text-transform": "uppercase", "text-letter-spacing": 0.16,
        "text-size": ["interpolate", ["linear"], ["zoom"], 11, 10, 15, 12.5], "text-max-width": 7, "text-padding": 6,
      },
      paint: { "text-color": label, ...halo },
    },
    {
      id: "town", type: "symbol", source: "omt", "source-layer": "place", minzoom: 8, maxzoom: 14,
      filter: classIn("town", "village"),
      layout: {
        "text-field": NAME, "text-font": ["Inter Medium"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 8, 11, 13, 14], "text-max-width": 7, "text-padding": 6,
      },
      paint: { "text-color": label, ...halo },
    },
    {
      id: "city", type: "symbol", source: "omt", "source-layer": "place", minzoom: 3, maxzoom: 12,
      filter: classIn("city"),
      layout: {
        "symbol-sort-key": ["coalesce", ["get", "rank"], 20],
        "text-field": NAME, "text-font": ["Inter SemiBold"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 3, 11, 10, 17], "text-max-width": 7, "text-padding": 8,
      },
      paint: { "text-color": ink, ...halo },
    },
    {
      id: "state", type: "symbol", source: "omt", "source-layer": "place", minzoom: 3, maxzoom: 7,
      filter: classIn("state", "province"),
      layout: {
        "text-field": NAME, "text-font": ["Inter Medium"], "text-transform": "uppercase", "text-letter-spacing": 0.16,
        "text-size": 10.5, "text-max-width": 6,
      },
      paint: { "text-color": label, ...halo },
    },
  ];

  return {
    version: 8,
    glyphs: `${FONTS}{fontstack}/{range}.pbf`,
    "font-faces": { "Inter Medium": face(latinExt500, latin500), "Inter SemiBold": face(latinExt600, latin600) },
    sources: { omt: { type: "vector", url: TILES } },
    // Built loosely above and checked by MapLibre when the style loads; its
    // layer types are a union too wide to write each layer against by hand.
    layers: layers as unknown as Layer[],
  };
}
