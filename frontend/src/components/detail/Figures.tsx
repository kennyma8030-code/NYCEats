import type { LedgerItem, WindowDays } from "../../api/types";
import { windowOf } from "../../state/filters";

interface Props {
  item: LedgerItem;
  window: WindowDays;
}

export function Figures({ item, window }: Props) {
  const W = windowOf(window);
  return (
    <div className="figs">
      <div>
        <b>{item.current.toLocaleString()}</b>
        <span>Mentions, last {W.long}</span>
      </div>
      <div>
        <b>{item.previous.toLocaleString()}</b>
        <span>Mentions, {W.long} before</span>
      </div>
      <div>
        <b>{item.total_mentions.toLocaleString()}</b>
        <span>Mentions, all time</span>
      </div>
    </div>
  );
}
