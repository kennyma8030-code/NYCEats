import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { Algo, LedgerItem, WindowDays } from "./api/types";
import { restaurantFromUrl, setRestaurantInUrl, useFilters } from "./state/filters";
import { useLedger } from "./hooks/useLedger";
import { useFacets } from "./hooks/useFacets";
import type { NameHit } from "./lib/search";
import { Rail } from "./components/rail/Rail";
import { LedgerList } from "./components/ledger/LedgerList";
import { DetailPanel } from "./components/detail/DetailPanel";
import "./App.css";

export default function App() {
  const { filters, update, toggleNeed, toggleFlaw, clear } = useFilters();
  const ledger = useLedger(filters);
  const facets = useFacets();

  // The selected row is kept after close so the panel can slide out with its
  // content intact; `open` is what actually shows it. `selectedWindow` is the
  // period its numbers were computed for.
  const [selected, setSelected] = useState<LedgerItem | null>(null);
  const [selectedWindow, setSelectedWindow] = useState<WindowDays>(filters.window);
  // ...and the ranking it was computed under: a flag only exists under v2.
  const [selectedAlgo, setSelectedAlgo] = useState<Algo>(filters.algo);
  const [open, setOpen] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  // Only the most recent pick may open; a slow earlier one must not win.
  const latestPick = useRef<string | null>(null);

  const select = useCallback((item: LedgerItem, window: WindowDays, algo: Algo) => {
    setSelected(item);
    setSelectedWindow(window);
    setSelectedAlgo(algo);
    setOpen(true);
  }, []);
  const selectRow = useCallback(
    (item: LedgerItem) => select(item, filters.window, filters.algo),
    [select, filters.window, filters.algo],
  );

  // The current list, only when it is for the period on screen: useFetch keeps
  // the previous result while the next one loads.
  const listed = ledger.data && ledger.data.window_days === filters.window ? ledger.data.items : null;

  /** Open any restaurant by key: its row from the list if it is there,
   *  otherwise the same row built for it alone. */
  const openKey = useCallback(
    (key: string) => {
      latestPick.current = key;
      const inList = listed?.find((i) => i.entity_key === key);
      if (inList) {
        setOpening(null);
        select(inList, filters.window, filters.algo);
        return;
      }
      setOpening(key);
      const window = filters.window;
      const algo = filters.algo;
      api.ledgerEntity(key, window, algo).then(
        (item) => {
          if (latestPick.current !== key) return;
          setOpening(null);
          select(item, window, algo);
        },
        () => {
          if (latestPick.current === key) setOpening(null);
        },
      );
    },
    [listed, filters.window, filters.algo, select],
  );
  const pick = useCallback((hit: NameHit) => openKey(hit.key), [openKey]);

  // Warm what search has highlighted, so opening it is immediate.
  const preview = useCallback(
    (key: string) => {
      api.ledgerEntity(key, filters.window, filters.algo).catch(() => {});
      api.restaurant(key, filters.algo).catch(() => {});
    },
    [filters.window, filters.algo],
  );

  // Keep the open restaurant's numbers on the period shown: from the list
  // when it is on it, otherwise fetched for it alone (a searched place).
  useEffect(() => {
    if (!selected) return;
    const fresh = listed?.find((i) => i.entity_key === selected.entity_key);
    if (fresh) {
      if (fresh !== selected) setSelected(fresh);
      if (selectedWindow !== filters.window) setSelectedWindow(filters.window);
      if (selectedAlgo !== filters.algo) setSelectedAlgo(filters.algo);
      return;
    }
    if (selectedWindow === filters.window && selectedAlgo === filters.algo) return;
    const key = selected.entity_key;
    const window = filters.window;
    const algo = filters.algo;
    api.ledgerEntity(key, window, algo).then(
      (item) => {
        setSelected((s) => (s?.entity_key === key ? item : s));
        setSelectedWindow(window);
        setSelectedAlgo(algo);
      },
      () => {},
    );
  }, [listed, selected, selectedWindow, selectedAlgo, filters.window, filters.algo]);

  // A shared link opens straight onto its restaurant.
  const initial = useRef(restaurantFromUrl());
  useEffect(() => {
    if (initial.current) openKey(initial.current);
    initial.current = null;
    // Once, on load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // While a shared link is still opening, leave its ?r= alone.
    if (!open && opening) return;
    setRestaurantInUrl(open && selected ? selected.entity_key : null);
  }, [open, selected, opening]);

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
          onToggleFlaw={toggleFlaw}
          onClear={clear}
          onPick={pick}
          onPreview={preview}
          opening={opening}
        />
        <LedgerList
          filters={filters}
          data={ledger.data}
          loading={ledger.loading}
          error={ledger.error}
          selectedKey={open ? selected?.entity_key ?? null : null}
          onSelect={selectRow}
          onClear={clear}
        />
      </div>
      <DetailPanel item={selected} open={open} window={selectedWindow} algo={selectedAlgo} onClose={close} />
    </>
  );
}
