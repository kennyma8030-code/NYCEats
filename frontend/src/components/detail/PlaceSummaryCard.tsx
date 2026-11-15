import type { PlaceSummary } from "../../api/types";
import { SUBREDDIT } from "../../state/city";

/** What the sub says about a place, in a model's words. The label says so in
 *  plain sight, and it is a paragraph rather than a quote, because it is a
 *  paraphrase. Most places have none, and then nothing renders. The count is
 *  the number of comments the model was sent, which the API cannot list by
 *  themselves, so it opens the place's own comment list beside the card: the
 *  comments the summary was written from are among those. */
interface Props {
  summary: PlaceSummary | null | undefined;
  onComments?: () => void;
}

export function PlaceSummaryCard({ summary, onComments }: Props) {
  if (!summary?.text) return null;
  const when = summary.written_at
    ? new Date(summary.written_at).toLocaleDateString("en-US", { month: "long", year: "numeric" })
    : null;
  const n = summary.comment_count;
  const count = n ? `from ${n.toLocaleString()} ${n === 1 ? "comment" : "comments"}` : null;
  return (
    <section className="ps" aria-label="AI summary of the comments">
      <p className="lab">
        AI summary of r/{SUBREDDIT}
        {count && " · "}
        {count && onComments ? (
          <button type="button" className="ps-count" title="Show this place's comments" onClick={onComments}>
            {count}
          </button>
        ) : (
          count
        )}
        {when && ` · ${when}`}
      </p>
      <p className="ps-text">{summary.text}</p>
    </section>
  );
}
