import { memo, useMemo } from "react";
import { wallColumns, type WallCard, type WallColumn } from "../../lib/wall";

// Three depths, far to near: how many columns, cards in each, and seconds
// for a loop (a base, and a step that staggers the columns). Far is small,
// faint and slow; near is large, sharp and fast. The sizes are in Home.css.
const LAYERS = [
  { depth: "far", columns: 7, per: 9, base: 150, step: 14 },
  { depth: "mid", columns: 4, per: 7, base: 95, step: 11 },
  { depth: "near", columns: 2, per: 5, base: 58, step: 9 },
] as const;

function Card({ card }: { card: WallCard }) {
  if (card.kind === "quote") {
    return (
      <div className="wall-card">
        <p className="wall-quote">{card.text}</p>
        <p className="wall-sub">{card.sub}</p>
      </div>
    );
  }
  return (
    <div className="wall-card">
      <p className="wall-label">{card.label}</p>
      <p className="wall-name">{card.text}</p>
      <p className="wall-sub">{card.stat}</p>
    </div>
  );
}

function Column({ column }: { column: WallColumn }) {
  return (
    <div className="wall-track" style={{ animationDuration: `${column.duration}s`, animationDelay: `${column.delay}s` }}>
      {column.cards.map((card, i) => <Card key={i} card={card} />)}
    </div>
  );
}

/** The drifting wall behind the title: real comments and real rankings,
 *  as decoration. It is hidden from screen readers and cannot be clicked;
 *  everything on it is reachable properly one screen down. */
export const Wall = memo(function Wall({ pool }: { pool: WallCard[] }) {
  const layers = useMemo(
    () => LAYERS.map((l) => ({ depth: l.depth, columns: wallColumns(pool, l.columns, l.per, l.base, l.step) })),
    [pool],
  );
  return (
    <div className={pool.length ? "wall ready" : "wall"} aria-hidden="true">
      {layers.map((l) => (
        <div key={l.depth} className={`wall-layer ${l.depth}`}>
          {l.columns.map((c, i) => <Column key={i} column={c} />)}
        </div>
      ))}
    </div>
  );
});
