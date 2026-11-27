// The words search understands without a model, matched as someone types.
//
// /api/search/vocabulary ships a city's cuisines, areas, dishes and
// descriptors once; the box then suggests them with no network, the way
// lib/search.ts suggests names. Picking one runs it as a search. Kept free of
// runtime imports so the matching can be tested on its own (frontend/tests).
import type { SearchVocabulary } from "../api/types";

export type TermKind = "cuisine" | "area" | "dish" | "tag";

export interface TermHit {
  kind: TermKind;
  label: string;
  /** Places for a cuisine or an area; mentions for a dish or a tag. */
  n: number;
}

/** Case, accents and punctuation out, so "Café" and "cafe" meet. */
export function fold(raw: string): string {
  return raw.toLowerCase().replace(/['’‘]/g, "").normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, " ").trim();
}

// Filters before things matched by meaning: a cuisine or an area narrows the
// answer exactly, which is what a short query usually wants.
const KINDS: [keyof SearchVocabulary, TermKind][] = [
  ["cuisines", "cuisine"], ["areas", "area"], ["dishes", "dish"], ["tags", "tag"],
];

/** Terms the typed text could be the start of: the whole label first, then a
 *  label starting with it, then a later word starting with it. */
export function matchTerms(v: SearchVocabulary, raw: string, limit = 3): TermHit[] {
  const q = fold(raw);
  if (q.length < 2) return [];
  const scored: { hit: TermHit; score: number; order: number }[] = [];
  const seen = new Set<string>();
  KINDS.forEach(([field, kind], order) => {
    for (const [label, n] of v[field] ?? []) {
      const s = fold(label);
      const score = s === q ? 3 : s.startsWith(q) ? 2 : s.includes(" " + q) ? 1 : 0;
      // A label two kinds share (pizza the cuisine, pizza the dish) is one
      // suggestion: either way picking it searches the same word.
      if (!score || seen.has(s)) continue;
      seen.add(s);
      scored.push({ hit: { kind, label, n }, score, order });
    }
  });
  scored.sort((a, b) => b.score - a.score || a.order - b.order || b.hit.n - a.hit.n);
  return scored.slice(0, limit).map((x) => x.hit);
}

/** "412 places" for what filters, "1,090 mentions" for what is matched by meaning. */
export function termCount(h: TermHit): string {
  const unit = h.kind === "cuisine" || h.kind === "area" ? "place" : "mention";
  return `${h.n.toLocaleString()} ${unit}${h.n === 1 ? "" : "s"}`;
}
