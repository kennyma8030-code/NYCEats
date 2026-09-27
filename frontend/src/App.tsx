import { useCallback, useEffect, useState } from "react";
import type { LedgerItem } from "./api/types";
import { useFilters } from "./state/filters";
import { useLedger } from "./hooks/useLedger";
import { useFacets } from "./hooks/useFacets";
import { Rail } from "./components/rail/Rail";
import { LedgerList } from "./components/ledger/LedgerList";
import { DetailPanel } from "./components/detail/DetailPanel";
import "./App.css";

export default function App() {
  const { filters, update, toggleNeed, clear } = useFilters();
  const ledger = useLedger(filters);
  const facets = useFacets();

  // The selected row is kept after close so the panel can slide out with its
  // content intact; `open` is what actually shows it.
  const [selected, setSelected] = useState<LedgerItem | null>(null);
  const [open, setOpen] = useState(false);

  // When the period or filters change, refresh the open row's numbers if it
  // is still in the list; otherwise keep showing what was clicked.
  useEffect(() => {
    if (!selected || !ledger.data) return;
    const fresh = ledger.data.items.find((i) => i.entity_key === selected.entity_key);
    if (fresh && fresh !== selected) setSelected(fresh);
  }, [ledger.data, selected]);

  const select = useCallback((item: LedgerItem) => {
    setSelected(item);
    setOpen(true);
  }, []);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    document.body.classList.toggle("split", open);
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <div className="page">
        <Rail
          filters={filters}
          facets={facets.data}
          onChange={update}
          onToggleNeed={toggleNeed}
          onClear={clear}
        />
        <LedgerList
          filters={filters}
          data={ledger.data}
          loading={ledger.loading}
          error={ledger.error}
          selectedKey={open ? selected?.entity_key ?? null : null}
          onSelect={select}
          onClear={clear}
        />
      </div>
      <DetailPanel item={selected} open={open} window={filters.window} onClose={close} />
    </>
  );
}
