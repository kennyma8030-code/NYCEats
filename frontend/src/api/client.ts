import type { Facets, LedgerResponse, Mention, Page, RestaurantDetail } from "./types";
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
  const p = new URLSearchParams({ category: f.category, window: String(f.window), limit: String(limit) });
  if (f.cuisine) p.set("cuisine", f.cuisine);
  if (f.borough) p.set("borough", f.borough);
  f.needs.forEach((n) => p.append("need", n));
  return p.toString();
}

const key = (k: string) => encodeURIComponent(k);

export const api = {
  ledger: (f: Filters, signal?: AbortSignal) =>
    get<LedgerResponse>(`/api/ledger?${ledgerParams(f)}`, signal),
  facets: (signal?: AbortSignal) => get<Facets>("/api/facets", signal),
  restaurant: (entityKey: string, signal?: AbortSignal) =>
    get<RestaurantDetail>(`/api/restaurants/${key(entityKey)}`, signal),
  mentions: (entityKey: string, offset: number, limit = 50, signal?: AbortSignal) =>
    get<Page<Mention>>(
      `/api/restaurants/${key(entityKey)}/mentions?sort=score&limit=${limit}&offset=${offset}`,
      signal,
    ),
};
