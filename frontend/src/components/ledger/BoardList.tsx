import type { BoardId, LedgerItem } from "../../api/types";
import { useBoard } from "../../hooks/useBoard";
import { BADGE_LABEL, boardExplainer, boardMetric, isRankable } from "../../lib/rating";
import { BOARDS, windowOf, type Filters } from "../../state/filters";
import { Sparkline } from "./Sparkline";
import "./LedgerList.css";

interface Props {
  filters: Filters;
  board: BoardId;
  onBoard: (b: BoardId) => void;
  selectedKey: string | null;
  onSelect: (item: LedgerItem) => void;
  onClear: () => void;
}

/** The boards: each tab ranks by one value of the rating, with the rest as
 *  badges and filters. There is no combined score. */
export function BoardList({ filters, board, onBoard, selectedKey, onSelect, onClear }: Props) {
  const { data, loading, error, current } = useBoard(board, filters.window, filters.cuisine, filters.borough);
  const W = windowOf(filters.window);
  const label = BOARDS.find((b) => b.id === board)?.label ?? board;
  const bits = [filters.cuisine, filters.borough].filter(Boolean);
  // The previous tab's rows only while this one loads, drawn dimmed; never
  // after a failure.
  const items = !error && data && (current || loading) ? data.items : [];
  const lines = data?.board === board ? data.lines : null;

  return (
    <main className="ledger">
      <h1>
        <em>{label}</em>
      </h1>
      <div className="tabs" role="group" aria-label="Board">
        {BOARDS.map((b) => (
          <button key={b.id} type="button" aria-pressed={b.id === board} onClick={() => onBoard(b.id)}>
            {b.label}
          </button>
        ))}
      </div>
      <p className="sum">
        {boardExplainer(board, lines)}
        {bits.length ? ` · ${bits.join(" · ")}` : ""}
      </p>

      {error && <p className="err">{error}</p>}

      {!error && current && items.length === 0 && !loading ? (
        <div className="empty">
          <p>Nothing on this board{bits.length ? " for these filters" : ""}.</p>
          {bits.length > 0 && (
            <button type="button" className="pill-button" onClick={onClear}>
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <ol className={`list${loading ? " busy" : ""}`} aria-busy={loading}>
          {items.map((item, i) => {
            const r = item.rating;
            const m = r ? boardMetric(board, r) : null;
            const where = [item.neighborhood, item.borough].filter(Boolean).join(", ");
            const meta = [item.cuisine, where].filter(Boolean).join(" · ");
            const badge = r && isRankable(r) ? r.badge : null;
            const on = item.entity_key === selectedKey;
            return (
              <li key={item.entity_key} className={`row${on ? " on" : ""}`}>
                <button
                  type="button"
                  className="hit"
                  aria-label={`${i + 1}. ${item.name}${m ? `, ${m.big} ${m.small}` : ""}${badge ? `, ${BADGE_LABEL[badge]}` : ""}`}
                  aria-current={on || undefined}
                  onClick={() => onSelect(item)}
                >
                  <span className="rk">{String(i + 1).padStart(2, "0")}</span>
                  <span>
                    <span className="nm">{item.name}</span>
                    {(meta || badge) && (
                      <span className="meta">
                        {badge && <span className={`bdg ${badge}`}>{BADGE_LABEL[badge]}</span>}
                        {meta}
                      </span>
                    )}
                  </span>
                  <Sparkline current={item.series} previous={item.previous_series} />
                  <span className="m">
                    <b className="good">{m?.big ?? "–"}</b>
                    <small>{m?.small ?? ""}</small>
                  </span>
                </button>
              </li>
            );
          })}
          {items.length === 0 && loading && Array.from({ length: 8 }, (_, i) => <li key={i} className="row skel" aria-hidden="true" />)}
        </ol>
      )}
      {items.length > 0 && <p className="sum">The line beside each row is mentions over the last {W.long}; the ranking does not use it.</p>}
    </main>
  );
}
