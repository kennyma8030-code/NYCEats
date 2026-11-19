// How wide the city view's panels are at a given window width. The styles
// take these numbers as custom properties (City.css) and the map takes them
// as its padding, so the two cannot disagree. Pure, so the arithmetic can be
// tested on its own (frontend/tests).

/** At or below this the panel is a sheet over the bottom of the map. */
export const PHONE = 720;
/** From this width the comments, once asked for, get a column of their own;
 *  under it they take the restaurant's panel. */
export const COLUMNS_MIN = 1300;

/** The panels' distance from the window's edge, and from each other. */
export const MARGIN = 24;
export const GAP = 12;

const BOARD = 408;        // the list, with its search, sorts and filters
const STRIP = 204;        // the list beside an open restaurant: rank and name
const PREVIEW = 300;      // a hovered row's preview
const PLACE = 480;        // an open restaurant, beside its comments
const PLACE_TABBED = 520; // an open restaurant showing its comments in its own panel
const PLACE_WIDE = 860;   // an open restaurant on its own: its boxes sit two abreast
const COMMENTS = 380;
const COMMENTS_MAX = 460;
const MAP_ROOM = 360;     // what a wide window keeps for the map before the comments widen
const MAP_MIN = 200;      // what the wide restaurant leaves the map before it narrows
const AIR = 32;           // between the last panel and anything the map centres

/** list: only the list. preview: a hovered row's preview beside it.
 *  open: a restaurant is open, on its own. comments: its comments are open too. */
export type CityState = "list" | "preview" | "open" | "comments";

export interface CityLayout {
  phone: boolean;
  /** The comments have their own column. */
  columns: boolean;
  board: number;
  /** 0 when there is no such panel. */
  place: number;
  comments: number;
  /** The x where the last panel ends. */
  covered: number;
}

export function cityLayout(width: number, state: CityState): CityLayout {
  const phone = width <= PHONE;
  const columns = state === "comments" && width >= COLUMNS_MIN;
  const board = state === "open" || state === "comments" ? STRIP : BOARD;
  // What is left beside the list, between the margins.
  const room = Math.max(0, width - 2 * MARGIN - board - GAP);
  // On its own the restaurant takes the width the comments would have had,
  // so that all of it fits without scrolling.
  const wide = Math.max(PLACE_TABBED, Math.min(PLACE_WIDE, room - MAP_MIN));
  const want = { list: 0, preview: PREVIEW, open: wide, comments: columns ? PLACE : PLACE_TABBED }[state];
  const place = Math.min(room, want);
  const spare = width - MARGIN - STRIP - GAP - PLACE - GAP - MARGIN - MAP_ROOM;
  const comments = columns ? Math.max(COMMENTS, Math.min(COMMENTS_MAX, spare)) : 0;
  const covered = MARGIN + board + (place ? GAP + place : 0) + (comments ? GAP + comments : 0);
  return { phone, columns, board, place, comments, covered };
}

/** The map's left and right padding on a wide screen: nothing is centred
 *  under a panel, and the right margin gives way before the map is squeezed
 *  to nothing. */
export function mapSides(width: number, layout: CityLayout): { left: number; right: number } {
  const left = layout.covered + AIR;
  return { left, right: width - left - 64 >= 160 ? 64 : 24 };
}

/** Where a preview's top goes: level with the row it belongs to, so the
 *  pointer reaches it by moving straight across, but never off the window. */
export function previewTop(rowTop: number, panelHeight: number, viewportHeight: number): number {
  const lowest = Math.max(MARGIN, viewportHeight - MARGIN - panelHeight);
  return Math.round(Math.max(MARGIN, Math.min(lowest, rowTop - 8)));
}
