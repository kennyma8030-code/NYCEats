import { useEffect, useRef } from "react";
import type { Facets, Flaw, Need } from "../../api/types";
import { activeFilterCount, type Filters } from "../../state/filters";
import { CategoryPicker } from "./CategoryPicker";
import { PeriodPicker } from "./PeriodPicker";
import { FilterControls } from "./FilterControls";
import { SearchBox } from "./SearchBox";
import { AlgoPicker } from "./AlgoPicker";
import { TopicBox } from "./TopicBox";
import type { NameHit } from "../../lib/search";
import "./Rail.css";

interface Props {
  filters: Filters;
  facets: Facets | null;
  onChange: (patch: Partial<Filters>) => void;
  onToggleNeed: (n: Need) => void;
  onToggleFlaw: (n: Flaw) => void;
  onClear: () => void;
  onPick: (hit: NameHit) => void;
  onPreview: (key: string) => void;
  opening: string | null;
}

export function Rail({ filters, facets, onChange, onToggleNeed, onToggleFlaw, onClear, onPick, onPreview, opening }: Props) {
  const more = useRef<HTMLDetailsElement>(null);
  const count = activeFilterCount(filters);

  // On wide screens the filters sit open in the rail; on phones they fold
  // into a disclosure.
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 861px)");
    const sync = () => {
      if (wide.matches && more.current) more.current.open = true;
    };
    sync();
    wide.addEventListener("change", sync);
    return () => wide.removeEventListener("change", sync);
  }, []);

  return (
    <aside className="rail">
      <p className="brand">
        NYCEats<span>New York</span>
      </p>
      <SearchBox onPick={onPick} onPreview={onPreview} opening={opening} />
      <div>
        <p className="lab">Ranking</p>
        <AlgoPicker value={filters.algo} onChange={(algo) => onChange({ algo })} />
      </div>
      <TopicBox value={filters.topic} onChange={(topic) => onChange({ topic })} />
      <CategoryPicker value={filters.category} onChange={(category) => onChange({ category })} />
      <div>
        <p className="lab">Period</p>
        <PeriodPicker value={filters.window} onChange={(window) => onChange({ window })} />
      </div>
      <details className="more" ref={more}>
        <summary>
          Filters <span>{count ? `${count} on` : ""}</span>
        </summary>
        <div className="fs-wrap">
          <FilterControls
            filters={filters}
            facets={facets}
            onChange={onChange}
            onToggleNeed={onToggleNeed}
            onToggleFlaw={onToggleFlaw}
            onClear={onClear}
          />
        </div>
      </details>
    </aside>
  );
}
