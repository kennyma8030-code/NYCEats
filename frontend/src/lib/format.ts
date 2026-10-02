import type { AspectKey, Category, LedgerItem } from "../api/types";

export const ASPECTS: AspectKey[] = ["food", "value", "service", "atmosphere", "wait"];

export const ASPECT_LABEL: Record<AspectKey, string> = {
  food: "Taste",
  value: "Value",
  service: "Service",
  atmosphere: "Room",
  wait: "Wait",
};

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

export function sentimentWord(v: number | null): string {
  if (v == null) return "Mixed";
  return v >= 0.5 ? "Loved" : v >= 0.25 ? "Liked" : "Mixed";
}

const plural = (n: number, one: string, many: string) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

/** The big number and its caption on the right of a ledger row. */
export function rowMetric(item: LedgerItem, category: Category): { big: string; small: string; good: boolean } {
  switch (category) {
    case "trending":
      return {
        big: signedCount(item.current - item.previous),
        small: `${item.current.toLocaleString()} vs ${plural(item.previous, "mention", "mentions")}`,
        good: true,
      };
    case "top":
      return { big: item.current.toLocaleString(), small: item.current === 1 ? "mention" : "mentions", good: false };
    case "gems":
      return { big: sentimentWord(item.sentiment), small: plural(item.current, "mention", "mentions"), good: true };
  }
}

/** Score in [-1, 1] -> filled bubbles out of 5: -1 = 0, -0.5 = 1.25, 0 = 2.5, 1 = 5. */
export const bubblesFilled = (score: number) => ((Math.max(-1, Math.min(1, score)) + 1) / 2) * 5;

const AVATAR = ["#0A7C66", "#C2410C", "#2B5FA8", "#8A5A12", "#7A3E9D", "#3E6B2F", "#A1344F"];
export function avatarColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (Math.imul(h, 31) + name.charCodeAt(i)) >>> 0;
  return AVATAR[h % AVATAR.length];
}

export function redditUrl(permalink: string | null): string | null {
  if (!permalink) return null;
  return permalink.startsWith("/") ? `https://www.reddit.com${permalink}` : permalink;
}

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
