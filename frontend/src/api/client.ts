import type {
  Algo, CommentSort, Facets, LedgerItem, LedgerResponse, Mention, NameRow, Page, RestaurantDetail, WindowDays,
} from "./types";
import type { Filters } from "../state/filters";

const BASE: string = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

// FastAPI reports failures as {detail} (a string, or a list of validation
// errors) and this API's database handler as {error, detail}.
async function readDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const d = body?.detail ?? body?.error;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? "").filter(Boolean).join("; ");
  } catch {
    /* not JSON */
  }
  return `${res.status} ${res.statusText}`.trim();
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(BASE + path, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) throw new ApiError(await readDetail(res), res.status);
  return (await res.json()) as T;
}

export function ledgerParams(f: Filters, limit = 50): string {
  const p = new URLSearchParams({
    algo: f.algo, category: f.category, window: String(f.window), limit: String(limit),
  });
  if (f.topic) p.set("topic", f.topic);
  if (f.cuisine) p.set("cuisine", f.cuisine);
  if (f.borough) p.set("borough", f.borough);
  f.needs.forEach((n) => p.append("need", n));
  f.flaws.forEach((n) => p.append("flaw", n));
  return p.toString();
}

const key = (k: string) => encodeURIComponent(k);

// Short-lived memo for per-restaurant reads. The scoring views only change
// when the worker refreshes them (~30 min), so reopening a restaurant, or
// opening one that search already prefetched on highlight, costs nothing.
// The request is NOT tied to any caller's AbortSignal: it is shared, and
// useFetch already discards results for a caller that has moved on.
const TTL = 5 * 60_000;
const memo = new Map<string, { at: number; value: Promise<unknown> }>();

function cached<T>(id: string, load: () => Promise<T>): Promise<T> {
  const hit = memo.get(id);
  if (hit && Date.now() - hit.at < TTL) return hit.value as Promise<T>;
  const value = load();
  memo.set(id, { at: Date.now(), value });
  value.catch(() => memo.delete(id)); // never cache a failure
  return value;
}

export const api = {
  ledger: (f: Filters, signal?: AbortSignal) =>
    get<LedgerResponse>(`/api/ledger?${ledgerParams(f)}`, signal),
  /** One restaurant as a ledger row for this window, ranked or not. */
  ledgerEntity: (entityKey: string, window: WindowDays, algo: Algo) =>
    cached(`le|${entityKey}|${window}|${algo}`, () =>
      get<LedgerItem>(`/api/ledger/entity?key=${key(entityKey)}&window=${window}&algo=${algo}`)),
  /** Every searchable name, as compact rows; see lib/search.ts. `v` is the
   *  row format: /api/names is browser-cached for 5 minutes, so a format
   *  change must change the URL or a stale copy is parsed as the new shape. */
  names: () => cached("names", () => get<NameRow[]>("/api/names?v=2")),
  facets: (signal?: AbortSignal) => get<Facets>("/api/facets", signal),
  restaurant: (entityKey: string, algo: Algo = "v1", _signal?: AbortSignal) =>
    cached(`r|${entityKey}|${algo}`, () =>
      get<RestaurantDetail>(`/api/restaurants/${key(entityKey)}?algo=${algo}`)),
  /** The complaints behind a flag under the new ranking. */
  standoutNegatives: (entityKey: string) =>
    cached(`neg|${entityKey}`, () =>
      get<Mention[]>(`/api/restaurants/${key(entityKey)}/standout-negatives?limit=5`)),
  mentions: (entityKey: string, sort: CommentSort, offset: number, limit = 50, signal?: AbortSignal) =>
    get<Page<Mention>>(
      `/api/restaurants/${key(entityKey)}/mentions?sort=${sort}&limit=${limit}&offset=${offset}`,
      signal,
    ),
};
