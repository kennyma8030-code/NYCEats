import type { LedgerItem, WindowDays } from "../../api/types";
import { capitalize, plural } from "../../lib/format";
import { windowOf } from "../../state/filters";

interface Props {
  item: LedgerItem;
  window: WindowDays;
  /** The commenters' own words for the place, most used first. */
  descriptors: string[];
}

const W = 340;
const H = 56;

// Both periods share one y scale so the comparison is honest.
function path(values: number[], max: number) {
  const step = W / Math.max(1, values.length - 1);
  return values.map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)} ${(H - 3 - (v / max) * (H - 8)).toFixed(1)}`).join("");
}

/** The counts behind the place, folded away: how often it comes up, how
 *  that compares with the period before, and what people call it. These
 *  measure attention, not liking, which is why they sit apart from the rating. */
export function Numbers({ item, window, descriptors }: Props) {
  const long = windowOf(window).long;
  const max = Math.max(1, ...item.series, ...item.previous_series);
  const now = item.series.length ? path(item.series, max) : "";
  const summary = `${plural(item.current, "mention", "mentions")} in the last ${long}, ${item.previous.toLocaleString()} in the ${long} before`;

  return (
    <details className="numbers">
      <summary>
        By the numbers
        <span className="numbers-chev" aria-hidden="true" />
      </summary>
      <dl className="figs">
        <div>
          <dt>Last {long}</dt>
          <dd>{item.current.toLocaleString()}</dd>
        </div>
        <div>
          <dt>{capitalize(long)} before</dt>
          <dd>{item.previous.toLocaleString()}</dd>
        </div>
        <div>
          <dt>All time</dt>
          <dd>{item.total_mentions.toLocaleString()}</dd>
        </div>
      </dl>
      <p className="place-quiet">
        Mentions in comments
        {item.distinct_authors ? `, from ${plural(item.distinct_authors, "person", "people")} in all` : ""}.
      </p>
      {now && (
        <figure className="trend">
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={summary}>
            {item.previous_series.length > 0 && <path className="trend-prev" d={path(item.previous_series, max)} />}
            <path className="trend-area" d={`${now}L${W} ${H}L0 ${H}Z`} />
            <path className="trend-line" d={now} />
          </svg>
          <figcaption>
            <span><i className="trend-key" />Last {long}</span>
            <span><i className="trend-key prev" />{capitalize(long)} before</span>
          </figcaption>
        </figure>
      )}
      {descriptors.length > 0 && (
        <>
          <p className="eyebrow">People call it</p>
          <div className="tags">
            {descriptors.map((d) => <span key={d} className="tag">{d}</span>)}
          </div>
        </>
      )}
    </details>
  );
}
