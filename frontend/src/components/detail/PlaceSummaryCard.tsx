import type { PlaceSummary } from "../../api/types";

/** What the sub says about a place, in a model's words. The label says so in
 *  plain sight, and it is a paragraph rather than a quote, because it is a
 *  paraphrase. Most places have none, and then nothing renders. The count is
 *  plain text: it is the number of comments the model was sent, not a list the
 *  API can open. */
export function PlaceSummaryCard({ summary }: { summary: PlaceSummary | null | undefined }) {
  if (!summary?.text) return null;
  const when = summary.written_at
    ? new Date(summary.written_at).toLocaleDateString("en-US", { month: "long", year: "numeric" })
    : null;
  const n = summary.comment_count;
  const label = [
    "AI summary of r/FoodNYC",
    n ? `from ${n.toLocaleString()} ${n === 1 ? "comment" : "comments"}` : null,
    when,
  ].filter(Boolean).join(" · ");
  return (
    <section className="ps" aria-label="AI summary of the comments">
      <p className="lab">{label}</p>
      <p className="ps-text">{summary.text}</p>
    </section>
  );
}
