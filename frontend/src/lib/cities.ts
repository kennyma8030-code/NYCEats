// Where each city is on the map. Only New York's places have coordinates
// (app/geo.py), so for every other city this is all the map knows: it opens
// centred here with no pins. Pure, so it can be tested (frontend/tests).

export interface CityView {
  /** [longitude, latitude], the order MapLibre takes. */
  center: [number, number];
  zoom: number;
}

const CITY_VIEWS: Record<string, CityView> = {
  FoodNYC: { center: [-73.972, 40.737], zoom: 11.4 },
  FoodLosAngeles: { center: [-118.3, 34.05], zoom: 9.9 },
  FoodSanDiego: { center: [-117.15, 32.76], zoom: 10.6 },
  austinfood: { center: [-97.743, 30.285], zoom: 11 },
  chicagofood: { center: [-87.66, 41.89], zoom: 10.8 },
  denverfood: { center: [-104.97, 39.74], zoom: 10.9 },
  FoodToronto: { center: [-79.39, 43.68], zoom: 10.8 },
};

// A subreddit added to the API before it is added here still opens: on the
// whole of North America rather than on the wrong city.
const UNKNOWN: CityView = { center: [-96, 39], zoom: 3.4 };

export const cityView = (subreddit: string): CityView => CITY_VIEWS[subreddit] ?? UNKNOWN;

/** The box to fit a list's pins in, as [[west, south], [east, north]], or
 *  null when there are too few to frame. The outermost twentieth on each
 *  side is left outside it once there are enough pins to spare them: one
 *  place on Staten Island should not shrink Manhattan to a thumbnail. Those
 *  pins are still on the map, a drag away. */
export function pinBounds(points: { lat: number; lng: number }[]): [[number, number], [number, number]] | null {
  if (points.length < 2) return null;
  const trim = points.length >= 10 ? Math.floor(points.length * 0.05) : 0;
  const span = (values: number[]): [number, number] => {
    const sorted = [...values].sort((a, b) => a - b);
    return [sorted[trim], sorted[sorted.length - 1 - trim]];
  };
  const [south, north] = span(points.map((p) => p.lat));
  const [west, east] = span(points.map((p) => p.lng));
  return [[west, south], [east, north]];
}
