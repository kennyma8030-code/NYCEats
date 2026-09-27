import { useLayoutEffect, useRef } from "react";
import type { LedgerItem, LedgerResponse } from "../../api/types";
import { activeFilterCount, categoryOf, NEEDS, windowOf, type Filters } from "../../state/filters";
import { LedgerRow } from "./LedgerRow";
import "./LedgerList.css";

interface Props {
  filters: Filters;
  data: LedgerResponse | null;
  loading: boolean;
  error: string | null;
  selectedKey: string | null;
  onSelect: (item: LedgerItem) => void;
  onClear: () => void;
}

const calm = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function LedgerList({ filters, data, loading, error, selectedKey, onSelect, onClear }: Props) {
  const W = windowOf(filters.window);
  const C = categoryOf(filters.category);
  const bits = [
    filters.cuisine,
    filters.borough,
    ...filters.needs.map((k) => NEEDS.find((n) => n.k === k)?.label.toLowerCase() ?? k),
  ].filter(Boolean);
  const filtered = activeFilterCount(filters) > 0;
  const items = data?.items ?? [];

  // FLIP: rows that move slide from their old position, new rows fade in.
  const listRef = useRef<HTMLOListElement>(null);
  const tops = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const next = new Map<string, number>();
    const animate = !calm() && tops.current.size > 0;
    list.querySelectorAll<HTMLLIElement>("li.row").forEach((li) => {
      const key = li.dataset.key!;
      const top = li.offsetTop;
      next.set(key, top);
      if (!animate) return;
      const prev = tops.current.get(key);
      if (prev === undefined) {
        li.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], {
          duration: 350,
          easing: "ease-out",
        });
      } else if (prev !== top) {
        li.animate([{ transform: `translateY(${prev - top}px)` }, { transform: "none" }], {
          duration: 550,
          easing: "cubic-bezier(.2,.7,.2,1)",
        });
      }
    });
    tops.current = next;
  }, [items]);

  return (
    <main className="ledger">
      <h1>
        <em>{C.label}</em> {filters.category === "gems" ? "of" : "over"} the last {W.long}
      </h1>
      <p className="sum">
        {C.hint}
        {bits.length ? ` · ${bits.join(" · ")}` : ""}
      </p>

      {error && <p className="err">{error}</p>}

      {!error && data && items.length === 0 && !loading ? (
        <div className="empty">
          <p>Nothing matches{filtered ? " these filters" : ""} for the last {W.long}.</p>
          {filtered && (
            <button type="button" className="pill-button" onClick={onClear}>
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <ol className={`list${loading ? " busy" : ""}`} ref={listRef} aria-busy={loading}>
          {items.map((item, i) => (
            <LedgerRow
              key={item.entity_key}
              item={item}
              rank={i + 1}
              category={filters.category}
              selected={item.entity_key === selectedKey}
              onSelect={onSelect}
            />
          ))}
          {!data && loading && Array.from({ length: 8 }, (_, i) => <li key={i} className="row skel" aria-hidden="true" />)}
        </ol>
      )}
    </main>
  );
}
