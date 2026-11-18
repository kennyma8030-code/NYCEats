const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const HOUR = 36e5;
const DAY = 24 * HOUR;

/** Reddit-style relative time: 5h ago, 12d ago, Mar 4, Mar 2023. */
export function ago(iso: string | null, now = Date.now()): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const d = now - t;
  if (d < HOUR) return "just now";
  if (d < DAY) return `${Math.floor(d / HOUR)}h ago`;
  if (d < 30 * DAY) return `${Math.floor(d / DAY)}d ago`;
  const x = new Date(t);
  return d < 365 * DAY ? `${MON[x.getMonth()]} ${x.getDate()}` : `${MON[x.getMonth()]} ${x.getFullYear()}`;
}

/** Change in mention count, signed: "+47", "-3", "0". */
export const signedCount = (n: number) => `${n > 0 ? "+" : ""}${n.toLocaleString()}`;

export const plural = (n: number, one: string, many: string) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

export function redditUrl(permalink: string | null): string | null {
  if (!permalink) return null;
  return permalink.startsWith("/") ? `https://www.reddit.com${permalink}` : permalink;
}

/** What a place is and where, on one line: "Pizza, Greenwich Village", or
 *  whichever half is known. A comma, because the area is whatever commenters
 *  called it ("near Bryant Park") and has to read after any cuisine. */
export const whereLine = (cuisine: string | null | undefined, area: string | null | undefined): string =>
  [cuisine, area].filter(Boolean).join(", ");

/** "November 2026", for a caption that says how fresh something is. */
export function monthYear(iso: string | null): string {
  const t = iso ? Date.parse(iso) : NaN;
  return Number.isNaN(t) ? "" : new Date(t).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
}

export const capitalize =(s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** The city's licences write addresses in capitals: "205 EAST HOUSTON STREET". */
export const titleCase = (s: string) => s.toLowerCase().replace(/(^|[\s-])([a-z])/g, (_, a: string, b: string) => a + b.toUpperCase());

const WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"];

/** A small count as a word, for a heading: "Seven cities". */
export const countWord = (n: number) => WORDS[n] ?? n.toLocaleString();
