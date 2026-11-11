import { useEffect, useRef } from "react";
import type { Facets, Flaw, Need } from "../../api/types";
import { activeFilterCount, boardFilterCount, type Filters, type View } from "../../state/filters";
import { CategoryPicker } from "./CategoryPicker";
import { PeriodPicker } from "./PeriodPicker";
import { FilterControls } from "./FilterControls";
import { SearchBox } from "./SearchBox";
import { AlgoPicker } from "./AlgoPicker";
import { TopicBox } from "./TopicBox";
import type { NameHit } from "../../lib/search";
import { useCities } from "../../hooks/useCities";
import { cityUrl, HOME, SUBREDDIT } from "../../state/city";
import "./Rail.css";

interface Props {
  view: View;
  onView: (v: View) => void;
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

export function Rail({ view, onView, filters, facets, onChange, onToggleNeed, onToggleFlaw, onClear, onPick, onPreview, opening }: Props) {
  const more = useRef<HTMLDetailsElement>(null);
  // A city appears here once it has a board. With only New York's there is
  // nothing to pick, and the brand reads as it always has.
  const cities = useCities().data ?? [];
  const city = cities.find((c) => c.subreddit === SUBREDDIT);
  const count = view === "boards" ? boardFilterCount(filters) : activeFilterCount(filters);

  // On wide screens the filters sit open in the rail; on phones they fold
  // into a disclosure. Re-run on coming back from the feed, which unmounts
  // them: the new <details> starts closed.
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 861px)");
    const sync = () => {
      if (wide.matches && more.current) more.current.open = true;
    };
    sync();
    wide.addEventListener("change", sync);
    return () => wide.removeEventListener("change", sync);
  }, [view]);

  return (
    <aside className="rail">
      <p className="brand">
        NYCEats
        {cities.length > 1 ? (
          <select
            className="city"
            aria-label="City"
            value={SUBREDDIT}
            // A new page, not a state change: see state/city.ts.
            onChange={(e) => window.location.assign(cityUrl(e.target.value, window.location.pathname))}
          >
            {!city && <option value={SUBREDDIT}>r/{SUBREDDIT}</option>}
            {cities.map((c) => (
              <option key={c.subreddit} value={c.subreddit}>{c.name}</option>
            ))}
          </select>
        ) : (
          <span>{city?.name ?? (SUBREDDIT === HOME ? "New York" : `r/${SUBREDDIT}`)}</span>
        )}
      </p>
      <nav className="views" aria-label="View">
        <button type="button" aria-pressed={view === "restaurants"} onClick={() => onView("restaurants")}>
          Restaurants
        </button>
        <button type="button" aria-pressed={view === "boards"} onClick={() => onView("boards")}>
          Boards
        </button>
        <button type="button" aria-pressed={view === "comments"} onClick={() => onView("comments")}>
          <i className="live" aria-hidden="true" />
          Live feed
        </button>
      </nav>
      {view !== "comments" && (
        <>
          <SearchBox onPick={onPick} onPreview={onPreview} opening={opening} />
          {view === "restaurants" && (
            <>
              <div>
                <p className="lab">Ranking</p>
                <AlgoPicker value={filters.algo} onChange={(algo) => onChange({ algo })} />
              </div>
              <TopicBox value={filters.topic} onChange={(topic) => onChange({ topic })} />
              <CategoryPicker value={filters.category} onChange={(category) => onChange({ category })} />
            </>
          )}
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
                boards={view === "boards"}
              />
            </div>
          </details>
        </>
      )}
    </aside>
  );
}
