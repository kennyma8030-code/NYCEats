import type { WindowDays } from "../../api/types";
import { capitalize } from "../../lib/format";
import { windowOf } from "../../state/filters";

interface Props {
  current: number[];
  previous: number[];
  window: WindowDays;
}

const W = 340;
const H = 48;

export function TrendChart({ current, previous, window }: Props) {
  const label = windowOf(window).long;
  const max = Math.max(1, ...current, ...previous);
  // Both periods share one y scale so the comparison is honest.
  const path = (v: number[]) =>
    v
      .map((x, i) => `${i ? "L" : "M"}${((i * W) / Math.max(1, v.length - 1)).toFixed(1)} ${(H - 3 - (x / max) * (H - 6)).toFixed(1)}`)
      .join("");
  const a = current.length ? path(current) : "";

  return (
    <div className="sh-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        {previous.length > 0 && <path className="pv" d={path(previous)} />}
        {a && <path className="ca" d={`${a}L${W} ${H}L0 ${H}Z`} />}
        {a && <path className="cl" d={a} />}
      </svg>
      <div className="sh-leg">
        <span><i />Last {label}</span>
        <span><i className="p" />{capitalize(label)} before</span>
      </div>
    </div>
  );
}
