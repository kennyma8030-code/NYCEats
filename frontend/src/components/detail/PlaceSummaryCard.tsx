import type { PlaceSummary } from "../../api/types";

/** What the sub says about a place, in a model's words. Labelled as a
 *  summary so it is never mistaken for a quote; most places have none, and
 *  then nothing renders. The count is plain text: it is the number of
 *  comments the summary was written from, not a list the API can open. */
export function PlaceSummaryCard({ summary }: { summary: PlaceSummary | null | undefined }) {
  if (!summary?.text) return null;
  const when = summary.written_at
    ? new Date(summary.written_at).toLocaleDateString("en-US", { month: "long", year: "numeric" })
    : null;
  const n = summary.comment_count;
  const label = [
    "What r/FoodNYC says",
    n ? `summarized from ${n.toLocaleString()} ${n === 1 ? "comment" : "comments"}` : "AI summary",
    when,
  ].filter(Boolean).join(" · ");
  return (
    <section className="ps" aria-label="AI summary of the comments">
      <p className="lab">{label}</p>
      <blockquote>{summary.text}</blockquote>
    </section>
  );
}
