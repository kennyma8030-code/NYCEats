import { useEffect, useRef, useState } from "react";
import type { Facets, Flaw, Need, WindowDays } from "../../api/types";
import { BRAND } from "../../brand";
import type { Ranking } from "../../hooks/useRanking";
import { SORTS, rowMetric, sortNote, sortOf } from "../../lib/sorts";
import { areaWords } from "../../state/city";
import { FLAWS, NEEDS, WINDOWS, windowOf } from "../../state/filters";
import { filterCount, flawLabel, isLedgerSort, needLabel, toggle, type Route } from "../../state/route";
import { Icon } from "../Icon";
import { Search, type Scope } from "../Search";

interface Props {
  route: Route;
  go: (patch: Partial<Route>) => void;
  scope: Scope;
  facets: Facets | null;
  ranking: Ranking;
  hot: string | null;
  onHot: (key: string | null) => void;
  onOpen: (key: string) => void;
}

type MenuId = "cuisine" | "area" | "needs" | "flaws" | "period";

/** The rating looks back a fixed number of days, whatever period is chosen. */
const daysPhrase = (days: number) => (days === 365 ? "12 months" : days % 30 === 0 ? `${days / 30} months` : `${days} days`);

/**
 * A city's panel while no restaurant is open: where you are, the search, the
 * sort, the filters and the numbered list. The list's numbers are the map's
 * pins: both are drawn from the same rows, in the same order.
 */
export function Leaderboard({ route, go, scope, facets, ranking, hot, onHot, onOpen }: Props) {
  const [menu, setMenu] = useState<MenuId | null>(null);
  const filters = useRef<HTMLDivElement>(null);
  const area = areaWords(route.city);
  const ledger = isLedgerSort(route.sort);
  const active = filterCount(route);

  // A menu closes on a click anywhere else and on Escape.
  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (!filters.current?.contains(e.target as Node) && !(e.target as Element).closest?.("[data-menu]")) setMenu(null);
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
  useEffect(() => setMenu(null), [route.city, route.sort]);

  const flip = (id: MenuId) => setMenu((m) => (m === id ? null : id));
  const { items, total, loading, error, current } = ranking;
  const pinned = items.filter((i) => i.location).length;

  const chip = (id: MenuId, label: string, value: string | null) => (
    <button
      type="button" className={value ? "chip on" : "chip"} aria-haspopup="true" aria-expanded={menu === id}
      onClick={() => flip(id)}
    >
      {value ?? label}
      <Icon name="down" size={12} stroke={2.4} />
    </button>
  );
  const several = <T,>(picked: T[], label: string, name: (k: T) => string) =>
    picked.length === 0 ? null : picked.length === 1 ? name(picked[0]) : `${label} · ${picked.length}`;

  return (
    <div className="board">
      <div className="board-head">
        <div className="board-top">
          <button type="button" className="back" onClick={() => go({ screen: "home" })}>
            <Icon name="left" />
            All cities
          </button>
          <span className="wordmark">{BRAND.first} <span>{BRAND.second}</span></span>
        </div>
        <div>
          <h1 className="board-city">{scope.name}</h1>
          <p className="board-src" data-menu>
            From r/{scope.subreddit} ·{" "}
            {ledger ? (
              <button type="button" className="period" aria-haspopup="true" aria-expanded={menu === "period"} onClick={() => flip("period")}>
                last {windowOf(ranking.window).long}
                <Icon name="down" size={12} stroke={2.4} />
              </button>
            ) : (
              `opinions from the last ${daysPhrase(ranking.lines?.window_days ?? 365)}`
            )}
          </p>
        </div>
        <Search
          scopes={[scope]} variant="panel" label={`Search restaurants in ${scope.name}`} placeholder="Search a restaurant or a dish"
          onPlace={(_, key) => onOpen(key)} onTopic={(_, topic) => go({ topic })}
        />
        <div className="seg" role="group" aria-label="Sort by">
          {SORTS.map((s) => (
            <button key={s.id} type="button" aria-pressed={route.sort === s.id} onClick={() => go({ sort: s.id })}>
              {s.label}
            </button>
          ))}
        </div>
        <div className="chips" ref={filters}>
          {route.topic && (
            <button type="button" className="chip on" onClick={() => go({ topic: "" })} aria-label={`Remove the topic ${route.topic}`}>
              “{route.topic}”
              <Icon name="close" size={12} stroke={2.4} />
            </button>
          )}
          {chip("cuisine", "Cuisine", route.cuisine || null)}
          {chip("area", area.one, route.borough || null)}
          {chip("needs", "Good for", several(route.needs, "Good for", needLabel))}
          {chip("flaws", "Complaints", several(route.flaws, "Complaints", flawLabel))}
          {active > 0 && (
            <button type="button" className="chip clear" onClick={() => go({ topic: "", cuisine: "", borough: "", needs: [], flaws: [] })}>
              Clear
            </button>
          )}

          {menu === "cuisine" && (
            <Menu label="Cuisine">
              <Choice on={!route.cuisine} onClick={() => { go({ cuisine: "" }); setMenu(null); }}>Any cuisine</Choice>
              {(facets?.cuisines ?? []).map((c) => (
                <Choice key={c.name} on={route.cuisine === c.name} count={c.n} onClick={() => { go({ cuisine: c.name }); setMenu(null); }}>
                  {c.name}
                </Choice>
              ))}
              {!facets && <p className="menu-note">Loading…</p>}
            </Menu>
          )}
          {menu === "area" && (
            <Menu label={area.one}>
              <Choice on={!route.borough} onClick={() => { go({ borough: "" }); setMenu(null); }}>{area.all}</Choice>
              {(facets?.boroughs ?? []).map((b) => (
                <Choice key={b.name} on={route.borough === b.name} count={b.n} onClick={() => { go({ borough: b.name }); setMenu(null); }}>
                  {b.name}
                </Choice>
              ))}
              {!facets && <p className="menu-note">Loading…</p>}
            </Menu>
          )}
          {menu === "needs" && (
            <Menu label="Good for" note={ledger ? null : "Filters Talked about and Trending, so choosing one switches to Talked about."}>
              {NEEDS.map((n) => (
                <Choice key={n.k} many on={route.needs.includes(n.k)} onClick={() => go({ needs: toggle<Need>(route.needs, n.k) })}>
                  {n.label}
                </Choice>
              ))}
            </Menu>
          )}
          {menu === "flaws" && (
            <Menu label="Complaints" note={ledger ? "Places among the worst tenth for it." : "Places among the worst tenth for it. Choosing one switches to Talked about."}>
              {FLAWS.map((n) => (
                <Choice key={n.k} many on={route.flaws.includes(n.k)} onClick={() => go({ flaws: toggle<Flaw>(route.flaws, n.k) })}>
                  {n.label}
                </Choice>
              ))}
            </Menu>
          )}
          {menu === "period" && (
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
          )}
        </div>
      </div>

      <p className="board-note">
        {sortNote(route.sort, ranking.window, ranking.lines)}
        {route.topic ? ` Only mentions under “${route.topic}” are counted.` : ""}
      </p>

      {error ? (
        <div className="board-msg" role="alert">
          <p>This list could not be loaded.</p>
          <p className="board-msg-sub">{error}</p>
          <button type="button" className="pill" onClick={ranking.retry}>Try again</button>
        </div>
      ) : current && !loading && items.length === 0 ? (
        <div className="board-msg">
          <p>{active ? "Nothing matches these filters." : route.sort === "trending" ? "Nothing is being talked about more than usual." : "Nothing to rank here yet."}</p>
          {active > 0 ? (
            <button type="button" className="pill" onClick={() => go({ topic: "", cuisine: "", borough: "", needs: [], flaws: [] })}>
              Clear filters
            </button>
          ) : route.sort === "trending" && (
            <p className="board-msg-sub">Try a longer period, above.</p>
          )}
        </div>
      ) : (
        <ol className={!current && items.length ? "rows busy" : "rows"} aria-busy={loading}>
          {items.map((item, i) => {
            const m = rowMetric(route.sort, item);
            const meta = [item.cuisine, item.neighborhood ?? item.borough].filter(Boolean).join(" · ");
            return (
              <li key={item.entity_key}>
                <button
                  type="button" className={hot === item.entity_key ? "row on" : "row"} data-key={item.entity_key}
                  onClick={() => onOpen(item.entity_key)}
                  onMouseEnter={() => onHot(item.entity_key)} onMouseLeave={() => onHot(null)}
                  onFocus={() => onHot(item.entity_key)} onBlur={() => onHot(null)}
                >
                  <span className={item.location ? "row-n" : "row-n off"} title={item.location ? undefined : "No known address, so no pin"}>
                    {i + 1}
                  </span>
                  <span className="row-main">
                    <span className="row-name">{item.name}</span>
                    {meta && <span className="row-meta">{meta}</span>}
                  </span>
                  <span className="row-num">
                    <b>{m.big}</b>
                    <small>{m.small}</small>
                  </span>
                </button>
              </li>
            );
          })}
          {items.length === 0 && Array.from({ length: 8 }, (_, i) => <li key={i} className="row-skel skel" aria-hidden="true" />)}
          {current && items.length > 0 && (
            <li className="rows-foot">
              {total > items.length ? `The top ${items.length} of ${total.toLocaleString()}. ` : ""}
              {pinned === 0
                ? `No pins yet: ${scope.name}'s places have no coordinates.`
                : pinned < items.length
                  ? "A grey number has no known address, so no pin."
                  : ""}
            </li>
          )}
        </ol>
      )}
    </div>
  );
}

function Menu({ label, note, children }: { label: string; note?: string | null; children: React.ReactNode }) {
  return (
    <div className="menu pop" role="menu" aria-label={label} data-menu>
      {note && <p className="menu-note">{note}</p>}
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
