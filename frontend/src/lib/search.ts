import { api } from "../api/client";
import type { NameRow } from "../api/types";

/**
 * Restaurant search, entirely in the browser.
 *
 * /api/names ships every restaurant with 2+ mentions (~10k, ~130 KB gzipped)
 * once; each keystroke then ranks locally with no network. At this size that
 * beats a request per letter, which over a phone connection is slower than
 * people type and arrives out of order.
 */

export interface NameHit {
  key: string;
  name: string;
  cuisine: string | null;
  borough: string | null;
  mentions: number;
  chain: boolean;
  closed: boolean;
  /** The alias that matched, when the match was on a spelling people typed
   *  rather than the name itself ("katz" for Katz's Delicatessen). */
  via: string | null;
}

interface Entry extends Omit<NameHit, "via"> {
  own: string[];      // normalized key and display name
  aliases: string[];  // normalized typed spellings that resolve here
  weight: number;     // popularity bonus, precomputed
}

/**
 * The same folding extract.py's normalize_entity applies to stored keys, so
 * the query and the names meet in one form: case, apostrophes (straight and
 * curly), accents, punctuation, "and", a leading "the", and a trailing
 * "restaurant"/"nyc". Without it "Katz’s" -- how a phone types it -- finds
 * nothing, because the key is "katzs".
 */
export function normalize(raw: string): string {
  let s = raw.toLowerCase().replace(/['’‘]/g, "");
  s = s.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  s = s.replace(/[^a-z0-9]+/g, " ").split(" ").filter((w) => w && w !== "and").join(" ");
  if (s.startsWith("the ")) s = s.slice(4);
  for (const suffix of [" restaurant", " nyc"]) if (s.endsWith(suffix)) s = s.slice(0, -suffix.length);
  return s.trim();
}

const capwords = (k: string) => k.split(" ").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");

let index: Promise<Entry[]> | null = null;

/** Download and index the names once; later calls share the same promise. */
export function loadNames(): Promise<Entry[]> {
  index ??= api.names().then((rows: NameRow[]) =>
      rows.map(([key, name, cuisine, borough, mentions, aliases, flags]) => {
        const display = name ?? capwords(key);
        const own = [...new Set([key, normalize(display)])];
        return {
          key, name: display, cuisine, borough, mentions,
          chain: (flags & 1) !== 0, closed: (flags & 2) !== 0,
          own,
          aliases: (aliases ?? []).map(normalize).filter((a) => a && !own.includes(a)),
          // log scale: 1,090 mentions is +42, 6 is +12. Enough that Katz's
          // beats "katzes" on "katz", not enough to drown a better match.
          weight: 14 * Math.log10(mentions + 1) - (flags & 2 ? 10 : 0),
        };
      }),
  ).catch((e: unknown) => {
    // .catch, not then's second argument: it must also cover a failure while
    // indexing the rows, or one bad load stays cached until a page reload.
    index = null;
    throw e;
  });
  return index;
}

/** How well one normalized string matches the query; 0 is no match. */
function matchScore(s: string, q: string, words: string[]): number {
  if (s === q) return 100;
  if (s.startsWith(q)) return 80;
  if (s.includes(" " + q)) return 60; // a later word starts with it
  // Every query word starts some word: "luger peter", "pizza joes".
  if (words.length > 1 && words.every((w) => (" " + s).includes(" " + w))) return 50;
  if (q.length >= 3 && s.includes(q)) return 30;
  return 0;
}

export function search(entries: Entry[], raw: string, limit = 7): NameHit[] {
  const q = normalize(raw);
  if (!q) return [];
  const words = q.split(" ");
  const scored: { e: Entry; score: number; via: string | null }[] = [];
  for (const e of entries) {
    let best = 0;
    let via: string | null = null;
    for (const s of e.own) best = Math.max(best, matchScore(s, q, words));
    // A typed spelling counts a little less than the name itself, so a
    // restaurant actually called "Grill" beats one people abbreviate that way.
    for (const a of e.aliases) {
      const m = matchScore(a, q, words) - 8;
      if (m > best) {
        best = m;
        via = a;
      }
    }
    if (best > 0) scored.push({ e, score: best + e.weight, via });
  }
  scored.sort((a, b) => b.score - a.score || b.e.mentions - a.e.mentions);
  return scored.slice(0, limit).map(({ e, via }) => toHit(e, via));
}

function toHit(e: Entry, via: string | null): NameHit {
  const { own: _o, aliases: _a, weight: _w, ...rest } = e;
  return { ...rest, via };
}

/** Character bigrams, for "did you mean" when nothing matches. */
function bigrams(s: string): Set<string> {
  const out = new Set<string>();
  const t = s.replace(/ /g, "");
  for (let i = 0; i < t.length - 1; i++) out.add(t.slice(i, i + 2));
  return out;
}

/** Closest names by bigram overlap (Dice), for a query with no match at all:
 *  "le bernadin", "coqadaq". Only runs on a miss, so a full scan is fine. */
export function suggest(entries: Entry[], raw: string, limit = 3): NameHit[] {
  const q = normalize(raw);
  if (q.length < 3) return [];
  const qb = bigrams(q);
  const scored: { e: Entry; score: number }[] = [];
  for (const e of entries) {
    let best = 0;
    for (const s of [...e.own, ...e.aliases]) {
      const sb = bigrams(s);
      let shared = 0;
      for (const g of qb) if (sb.has(g)) shared++;
      best = Math.max(best, (2 * shared) / (qb.size + sb.size || 1));
    }
    if (best >= 0.5) scored.push({ e, score: best + e.weight / 400 });
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map(({ e }) => toHit(e, null));
}
