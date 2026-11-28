import { memo, useEffect, useRef, useState } from "react";
import type { Facets, LedgerItem, Need, WindowDays } from "../../api/types";
import { BRAND } from "../../brand";
import type { RowHover } from "../../hooks/useHoverPreview";
import type { Ranking } from "../../hooks/useRanking";
import { PIN_LIMIT, RANKING_PAGE } from "../../lib/paging";
import { SORTS, rowMetric, sortOf } from "../../lib/sorts";
import { areaWords } from "../../state/city";
import { NEEDS, WINDOWS, windowOf } from "../../state/filters";
import { filterCount, isLedgerSort, needLabel, toggle, type Route, type SortId } from "../../state/route";
import { Icon } from "../Icon";
import { Search, type Scope } from "../Search";
import { SearchResults } from "../search/SearchResults";

interface Props {
  route: Route;
  go: (patch: Partial<Route>) => void;
  scope: Scope;
  facets: Facets | null;
  ranking: Ranking;
  hot: string | null;
  onHot: (key: string | null) => void;
  onOpen: (key: string) => void;
  /** The open restaurant. While there is one the list is a narrow strip of
   *  ranks and names beside it, still clickable to change restaurant. */
  selected: string | null;
  /** Opens a preview beside a row the pointer rests on. */
  hover: RowHover;
}

type MenuId = "cuisine" | "area" | "needs" | "period";

/** The rating looks back a fixed number of days, whatever period is chosen. */
const daysPhrase = (days: number) => (days === 365 ? "12 months" : days % 30 === 0 ? `${days / 30} months` : `${days} days`);

/**
 * A city's list: where you are, the search, the sort, the filters and the
 * rows. The rows are the map's pins: both are drawn from the same rows, in
 * the same order. Beside an open restaurant only the names are left.
 */
export function Leaderboard({ route, go, scope, facets, ranking, hot, onHot, onOpen, selected, hover }: Props) {
  const compact = selected !== null;
  const [menu, setMenu] = useState<MenuId | null>(null);
  const filters = useRef<HTMLDivElement>(null);
  const area = areaWords(route.city);
  const ledger = isLedgerSort(route.sort);
  const active = filterCount(route);

  // The period's popover closes on a click anywhere else; a filter opens and
  // closes only by its own chip. Escape closes either.
  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (menu === "period" && !(e.target as Element).closest?.("[data-menu]")) setMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setMenu(null);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [menu]);
  useEffect(() => setMenu(null), [route.city, route.sort, compact]);

  const flip = (id: MenuId) => setMenu((m) => (m === id ? null : id));
  const { items, total, loading, error, current, hasMore, loadingMore, moreError, loadMore } = ranking;
  // What the foot of the list has to say. With nothing to say there is no
  // foot: a short list ends at its last row, not at an empty padded line.
  const ended = !hasMore && !moreError && items.length > RANKING_PAGE;
  const pinNote = items.length > PIN_LIMIT ? ` The map shows the first ${PIN_LIMIT.toLocaleString()}.` : "";
  const foot = current && items.length > 0 && !compact && (moreError !== null || hasMore || ended || pinNote !== "");

  // The list has no end but its last place: the next page is asked for as
  // the reader nears the bottom. The mark watched is a tall invisible box
  // reaching up from the foot, so the request leaves a few screens early
  // whichever element is scrolling (the rows on a desk, the sheet on a
  // phone). Watched afresh after every page, so a page too short to push
  // the mark out of view asks for the next one too. A failed page waits for
  // the reader to ask again, or it would retry in a loop.
  const mark = useRef<HTMLSpanElement>(null);
  const moreRef = useRef(loadMore);
  moreRef.current = loadMore;
  const waiting = current && hasMore && !loadingMore && !moreError;
  useEffect(() => {
    const el = mark.current;
    if (!el || !waiting || typeof IntersectionObserver === "undefined") return;
    const seen = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) moreRef.current();
    });
    seen.observe(el);
    return () => seen.disconnect();
  }, [waiting, items.length]);

  const chip = (id: MenuId, label: string, value: string | null) => (
    <button
      type="button" className={value ? "chip on" : "chip"} aria-haspopup="true" aria-expanded={menu === id}
      onClick={() => flip(id)}
    >
      <span className="chip-text">{value ?? label}</span>
      <Icon name="right" size={12} stroke={2.4} className="chip-go" />
    </button>
  );
  const several = <T,>(picked: T[], label: string, name: (k: T) => string) =>
    picked.length === 0 ? null : picked.length === 1 ? name(picked[0]) : `${label} (${picked.length})`;

  const periodMenu = menu === "period" && (
    <Menu label="Period">
      {WINDOWS.map((w) => (
        <Choice
          key={w.d} on={ranking.window === w.d}
          onClick={() => { go({ window: w.d === sortOf(route.sort).window ? null : (w.d as WindowDays) }); setMenu(null); }}
        >
          Last {w.long}
        </Choice>
      ))}
    </Menu>
  );

  return (
    <div className={compact ? "board compact" : "board"}>
      {!compact && (
        <div className="rail">
          <button type="button" className="back" onClick={() => go({ screen: "home" })}>
            <Icon name="left" />
            All cities
          </button>
          <div className="rail-group rail-sorts" role="group" aria-label="Sort by">
            <p className="rail-label">Sort</p>
            {SORTS.map((s) => (
              <button key={s.id} type="button" className="sort" aria-pressed={!route.q && route.sort === s.id} onClick={() => go({ sort: s.id })}>
                {s.label}
              </button>
            ))}
          </div>
          <div className="rail-group chips" ref={filters}>
            <p className="rail-label">Filter</p>
            {route.topic && (
              <button type="button" className="chip on" onClick={() => go({ topic: "" })} aria-label={`Remove the topic ${route.topic}`}>
                <span className="chip-text">“{route.topic}”</span>
                <Icon name="close" size={12} stroke={2.4} className="chip-go" />
              </button>
            )}
            {chip("cuisine", "Cuisine", route.cuisine || null)}
            {menu === "cuisine" && (
              <Menu inline label="Cuisine">
                <Choice on={!route.cuisine} onClick={() => { go({ cuisine: "" }); setMenu(null); }}>Any cuisine</Choice>
                {(facets?.cuisines ?? []).map((c) => (
                  <Choice key={c.name} on={route.cuisine === c.name} count={c.n} onClick={() => { go({ cuisine: c.name }); setMenu(null); }}>
                    {c.name}
                  </Choice>
                ))}
                {!facets && <p className="menu-note">Loading…</p>}
              </Menu>
            )}
            {chip("area", area.one, route.borough || null)}
            {menu === "area" && (
              <Menu inline label={area.one}>
                <Choice on={!route.borough} onClick={() => { go({ borough: "" }); setMenu(null); }}>{area.all}</Choice>
                {(facets?.boroughs ?? []).map((b) => (
                  <Choice key={b.name} on={route.borough === b.name} count={b.n} onClick={() => { go({ borough: b.name }); setMenu(null); }}>
                    {b.name}
                  </Choice>
                ))}
                {!facets && <p className="menu-note">Loading…</p>}
              </Menu>
            )}
            {chip("needs", "Good for", several(route.needs, "Good for", needLabel))}
            {menu === "needs" && (
              <Menu inline label="Good for">
                {NEEDS.map((n) => (
                  <Choice key={n.k} many on={route.needs.includes(n.k)} onClick={() => go({ needs: toggle<Need>(route.needs, n.k) })}>
                    {n.label}
                  </Choice>
                ))}
              </Menu>
            )}
            {active > 0 && (
              <button type="button" className="chip clear" onClick={() => go({ topic: "", cuisine: "", borough: "", needs: [], flaws: [] })}>
                Clear
              </button>
            )}

          </div>
          <span className="wordmark">{BRAND.first} <span>{BRAND.second}</span></span>
        </div>
      )}
      <div className="board-body">
      {compact ? (
        <div className="board-head">
          {/* What the names below are: a search's answer is not a sort's ranking. */}
          <p className="eyebrow">{route.q ? `“${route.q}”` : sortOf(route.sort).label}</p>
          <h1 className="board-city">{scope.name}</h1>
        </div>
      ) : (
        <div className="board-head">
          <div>
            <h1 className="board-city">{scope.name}</h1>
            <div className="board-src" data-menu>
              From r/{scope.subreddit},{" "}
              {ledger ? (
                <button type="button" className="period" aria-haspopup="true" aria-expanded={menu === "period"} onClick={() => flip("period")}>
                  last {windowOf(ranking.window).long}
                  <Icon name="down" size={12} stroke={2.4} />
                </button>
              ) : (
                `last ${daysPhrase(ranking.lines?.window_days ?? 365)}`
              )}
              {periodMenu}
            </div>
          </div>
          <Search
            scopes={[scope]} variant="panel" label={`Search restaurants in ${scope.name}`} placeholder="Search a restaurant or a dish"
            onPlace={(_, key) => onOpen(key)} onSearch={(_, q) => go({ q })}
          />
        </div>
      )}

      {route.q ? (
        // Beside an open restaurant too: the ranking is not loaded under a
        // search (App.tsx), so the strip of names is the search's own answer,
        // never rows of a list nobody asked for.
        <SearchResults
          query={route.q} city={route.city} dev={route.dev} compact={compact}
          hot={hot} onHot={onHot} selected={selected} hover={hover} onOpen={onOpen} onClose={() => go({ q: "" })}
        />
      ) : error ? (
        <div className="board-msg" role="alert">
          <p>This list could not be loaded.</p>
          <p className="board-msg-sub">{error}</p>
          <button type="button" className="pill" onClick={ranking.retry}>Try again</button>
        </div>
      ) : current && !loading && items.length === 0 ? (
        <div className="board-msg">
          <p>{active ? "Nothing matches these filters." : "Nothing to rank here yet."}</p>
          {active > 0 && (
            <button type="button" className="pill" onClick={() => go({ topic: "", cuisine: "", borough: "", needs: [], flaws: [] })}>
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <ol className={!current && items.length ? "rows busy" : "rows"} aria-busy={loading} onScroll={hover.follow}>
          {items.map((item) => (
            <Row
              key={item.entity_key} item={item} sort={route.sort} on={hot === item.entity_key || selected === item.entity_key}
              current={selected === item.entity_key} compact={compact} onOpen={onOpen} onHot={onHot} hover={hover}
            />
          ))}
          {items.length === 0 && Array.from({ length: 8 }, (_, i) => <li key={i} className="row-skel skel" aria-hidden="true" />)}
          {foot && (
            <li className="rows-foot">
              <span className="rows-mark" ref={mark} aria-hidden="true" />
              {moreError ? (
                <>
                  The rest of the list could not be loaded.{" "}
                  <button type="button" className="textlink" onClick={loadMore}>Try again</button>
                </>
              ) : loadingMore ? (
                `Loading more of ${total.toLocaleString()}…`
              ) : hasMore && (
                // Scrolling asks for the next page by itself where it can.
                // The button is for where it cannot: a browser without the
                // observer, or a list folded down so its foot is never seen.
                <button type="button" className="textlink" onClick={loadMore}>Show more</button>
              )}
              {/* Only the end is announced: a reader of the screen is not told of every page. */}
              <span aria-live="polite">{ended && `All ${items.length.toLocaleString()} places.`}</span>
              {pinNote}
            </li>
          )}
        </ol>
      )}
      </div>
    </div>
  );
}

interface RowProps {
  item: LedgerItem;
  sort: SortId;
  /** Lit: the pointer is on it or on its pin, or it is the open restaurant. */
  on: boolean;
  current: boolean;
  compact: boolean;
  onOpen: (key: string) => void;
  onHot: (key: string | null) => void;
  hover: RowHover;
}

/** One place of the list. Memoised because a list runs to thousands of rows
 *  and the pointer moving over them changes only two: the one it left and
 *  the one it is on. Everything it is given keeps its identity between
 *  renders, so the rest are skipped. */
const Row = memo(function Row({ item, sort, on, current, compact, onOpen, onHot, hover }: RowProps) {
  const m = rowMetric(sort, item);
  const area = item.neighborhood ?? item.borough;
  const key = item.entity_key;
  return (
    <li>
      <button
        type="button" className={on ? "row on" : "row"} data-key={key}
        aria-current={current ? "true" : undefined} title={compact ? item.name : undefined}
        onClick={() => onOpen(key)}
        // A finger has no hover: only a mouse opens the preview, and
        // only focus that came from the keyboard does.
        onPointerEnter={(e) => {
          if (e.pointerType !== "mouse") return;
          onHot(key);
          hover.enter(key);
        }}
        onPointerLeave={(e) => {
          if (e.pointerType !== "mouse") return;
          onHot(null);
          hover.leave();
        }}
        onFocus={(e) => {
          onHot(key);
          if (e.currentTarget.matches(":focus-visible")) hover.focus(key);
        }}
        onBlur={() => {
          onHot(null);
          hover.leave();
        }}
      >
        <span className="row-main">
          <span className="row-name">{item.name}</span>
          {(item.cuisine || area) && (
            <span className="row-meta">
              {item.cuisine && <span className="row-cuisine">{item.cuisine}</span>}
              {area && <span className="row-area">{area}</span>}
            </span>
          )}
        </span>
        <span className="row-num">
          <b>{m.big}</b>
          <small>{m.small}</small>
        </span>
      </button>
    </li>
  );
});

/** inline: an accordion panel under its chip, pushing what follows down;
 *  otherwise a popover. */
function Menu({ label, inline, children }: { label: string; inline?: boolean; children: React.ReactNode }) {
  return (
    <div className={inline ? "acc" : "menu pop"} role="menu" aria-label={label} data-menu={inline ? undefined : true}>
      {children}
    </div>
  );
}

interface ChoiceProps {
  on: boolean;
  /** One of several that can be ticked together, rather than one of a set. */
  many?: boolean;
  count?: number;
  onClick: () => void;
  children: React.ReactNode;
}

function Choice({ on, many, count, onClick, children }: ChoiceProps) {
  return (
    <button type="button" className="choice" role={many ? "menuitemcheckbox" : "menuitemradio"} aria-checked={on} onClick={onClick}>
      <span className="choice-tick">{on && <Icon name="check" size={14} stroke={2.6} />}</span>
      <span className="choice-label">{children}</span>
      {count != null && <span className="choice-n">{count.toLocaleString()}</span>}
    </button>
  );
}
