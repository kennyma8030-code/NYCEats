import type { Facets, Need } from "../../api/types";
import { activeFilterCount, NEEDS, type Filters } from "../../state/filters";

interface Props {
  filters: Filters;
  facets: Facets | null;
  onChange: (patch: Partial<Filters>) => void;
  onToggleNeed: (n: Need) => void;
  onClear: () => void;
}

// Keep a selected value listed even before facets arrive (or if it has
// dropped out of them), so the select never silently shows "All".
function options(values: string[], selected: string) {
  return selected && !values.includes(selected) ? [selected, ...values] : values;
}

export function FilterControls({ filters, facets, onChange, onToggleNeed, onClear }: Props) {
  const cuisines = options((facets?.cuisines ?? []).map((f) => f.name).sort(), filters.cuisine);
  const boroughs = options((facets?.boroughs ?? []).map((f) => f.name), filters.borough);

  return (
    <>
      <div className="fs">
        <label className="lab" htmlFor="f-cuisine">Cuisine</label>
        <select
          id="f-cuisine"
          className="sel"
          value={filters.cuisine}
          onChange={(e) => onChange({ cuisine: e.target.value })}
        >
          <option value="">All cuisines</option>
          {cuisines.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
      <div className="fs">
        <label className="lab" htmlFor="f-borough">Borough</label>
        <select
          id="f-borough"
          className="sel"
          value={filters.borough}
          onChange={(e) => onChange({ borough: e.target.value })}
        >
          <option value="">All boroughs</option>
          {boroughs.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
      </div>
      <div className="fs">
        <p className="lab">Known for</p>
        <div className="needs" role="group" aria-label="Known for">
          {NEEDS.map((n) => (
            <button
              key={n.k}
              type="button"
              aria-pressed={filters.needs.includes(n.k)}
              onClick={() => onToggleNeed(n.k)}
            >
              {n.label}
            </button>
          ))}
        </div>
      </div>
      {activeFilterCount(filters) > 0 && (
        <button type="button" className="clear" onClick={onClear}>
          Clear filters
        </button>
      )}
    </>
  );
}
