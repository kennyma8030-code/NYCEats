// The landing page's wall of drifting cards: which comments and places go on
// it, and how they are dealt into columns. Pure, so it can be tested without
// a browser (frontend/tests).
import type { FeedItem, LedgerItem } from "../api/types";
import type { SortId } from "../state/route";
import { cardStat, sortOf } from "./sorts.ts";

export type WallCard =
  | { kind: "quote"; text: string; sub: string }
  | { kind: "place"; label: string; text: string; stat: string };

export interface WallColumn {
  /** The cards twice over, so the loop can restart without a jump. */
  cards: WallCard[];
  /** Seconds for one loop, and how far into it the column starts. */
  duration: number;
  delay: number;
}

const QUOTE_MIN = 24;
const QUOTE_MAX = 130;

/** A comment as one line for a card, or null when it will not make one: a
 *  link, a quote of someone else, a list, or too long to cut cleanly. */
export function quoteLine(body: string): string | null {
  const text = body.replace(/\s+/g, " ").trim();
  if (/https?:|\[|\]|^>|&gt;|\*\*|^\W*$/.test(text)) return null;
  if (text.length < QUOTE_MIN) return null;
  if (text.length <= QUOTE_MAX) return text;
  // The opening sentences that fit, when the comment opens with short ones.
  const sentences = text.match(/[^.!?]+[.!?]+/g) ?? [];
  let line = "";
  for (const s of sentences) {
    if ((line + s).trim().length > QUOTE_MAX) break;
    line += s;
  }
  line = line.trim();
  return line.length >= QUOTE_MIN ? line : null;
}

/** The comments worth a card, best liked first: those that name a place, are
 *  still on Reddit, and read as one line. */
export function wallQuotes(feed: FeedItem[], subreddit: string, limit = 24): WallCard[] {
  const out: { card: WallCard; score: number }[] = [];
  const seen = new Set<string>();
  for (const item of feed) {
    if (item.kind !== "comment" || item.was_deleted_later || !item.places.length) continue;
    const text = quoteLine(item.body);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    out.push({ card: { kind: "quote", text, sub: `r/${subreddit} on ${item.places[0].name}` }, score: item.score ?? 0 });
  }
  // A stable sort: among equals the newer comment, which came first, stays first.
  return out.sort((a, b) => b.score - a.score).slice(0, limit).map((x) => x.card);
}

export function wallPlaces(id: SortId, items: LedgerItem[], limit = 8): WallCard[] {
  const s = sortOf(id);
  return items.slice(0, limit).flatMap((item) => {
    const stat = cardStat(id, item, s.window);
    return stat ? [{ kind: "place" as const, label: s.full, text: item.name, stat }] : [];
  });
}

/** One pool, comments and places alternating for as long as both last, with
 *  the three rankings taking turns among the places. */
export function wallPool(quotes: WallCard[], rankings: WallCard[][]): WallCard[] {
  const places: WallCard[] = [];
  const longest = Math.max(0, ...rankings.map((r) => r.length));
  for (let i = 0; i < longest; i++) for (const r of rankings) if (r[i]) places.push(r[i]);
  const pool: WallCard[] = [];
  for (let i = 0; i < Math.max(quotes.length, places.length); i++) {
    if (quotes[i]) pool.push(quotes[i]);
    if (places[i]) pool.push(places[i]);
  }
  return pool;
}

/** Deal the pool into `count` columns of `per` cards. The strides are odd
 *  and the offsets differ by column, so neighbours never show the same card
 *  side by side; durations and starting points differ so they never move in
 *  step either. */
export function wallColumns(pool: WallCard[], count: number, per: number, base: number, step: number): WallColumn[] {
  if (!pool.length) return [];
  const columns: WallColumn[] = [];
  for (let c = 0; c < count; c++) {
    const cards: WallCard[] = [];
    for (let i = 0; i < per; i++) cards.push(pool[(c * 7 + i * 3 + c) % pool.length]);
    const duration = base + ((c * 37) % 5) * step;
    columns.push({ cards: cards.concat(cards), duration, delay: -((c * 13) % duration) });
  }
  return columns;
}
