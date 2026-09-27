import { useEffect, useRef } from "react";
import type { Facets, Need } from "../../api/types";
import { activeFilterCount, type Filters } from "../../state/filters";
import { CategoryPicker } from "./CategoryPicker";
import { PeriodPicker } from "./PeriodPicker";
import { FilterControls } from "./FilterControls";
import "./Rail.css";

interface Props {
  filters: Filters;
  facets: Facets | null;
  onChange: (patch: Partial<Filters>) => void;
  onToggleNeed: (n: Need) => void;
  onClear: () => void;
}

export function Rail({ filters, facets, onChange, onToggleNeed, onClear }: Props) {
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
            onClear={onClear}
          />
        </div>
      </details>
    </aside>
  );
}
