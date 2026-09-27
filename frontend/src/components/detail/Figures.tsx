import type { LedgerItem, WindowDays } from "../../api/types";
import { signedPct } from "../../lib/format";
import { windowOf } from "../../state/filters";

interface Props {
  item: LedgerItem;
  window: WindowDays;
}

export function Figures({ item, window }: Props) {
  const W = windowOf(window);
  const tone = item.change_pct == null ? undefined : item.change_pct >= 0 ? "pos" : "neg";
  return (
    <div className="figs">
      <div>
        <b>{item.current.toLocaleString()}</b>
        <span>Mentions, last {W.long}</span>
      </div>
      <div>
        <b className={tone}>{signedPct(item.change_pct)}</b>
        <span>vs {W.long} before</span>
      </div>
      <div>
        <b>{item.total_mentions.toLocaleString()}</b>
        <span>Mentions, all time</span>
      </div>
    </div>
  );
}
