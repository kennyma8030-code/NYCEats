import { memo, useEffect, useRef } from "react";
import type { Category, LedgerItem } from "../../api/types";
import { rowMetric } from "../../lib/format";
import { Sparkline } from "./Sparkline";

interface Props {
  item: LedgerItem;
  rank: number;
  category: Category;
  selected: boolean;
  onSelect: (item: LedgerItem) => void;
}

export const LedgerRow = memo(function LedgerRow({ item, rank, category, selected, onSelect }: Props) {
  const m = rowMetric(item, category);
  const where = [item.neighborhood, item.borough].filter(Boolean).join(", ");
  const meta = [item.cuisine, where].filter(Boolean).join(" · ");
  const ref = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  return (
    <li className={`row${selected ? " on" : ""}`} data-key={item.entity_key} ref={ref}>
      <button
        type="button"
        className="hit"
        aria-label={`${rank}. ${item.name}, ${m.big} ${m.small}`}
        aria-current={selected || undefined}
        onClick={() => onSelect(item)}
      >
        <span className="rk">{String(rank).padStart(2, "0")}</span>
        <span>
          <span className="nm">{item.name}</span>
          {(meta || item.flagged) && (
            <span className="meta">
              {item.flagged && (
                <span
                  className="flag"
                  title={`${item.strong_neg_people} people had a bad time here in the last two years`}
                >
                  ⚑ complaints
                </span>
              )}
              {meta}
            </span>
          )}
        </span>
        <Sparkline current={item.series} previous={item.previous_series} />
        <span className="m">
          <b className={m.good ? "good" : undefined}>{m.big}</b>
          <small>{m.small}</small>
        </span>
      </button>
    </li>
  );
});
