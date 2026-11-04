import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { CategoryVoice, CommentSort, RatingCategory, Voice } from "../../api/types";
import { usePaged } from "../../hooks/usePaged";
import { RedditComment } from "./RedditComment";
import "./CommentList.css";

/** Which comments a number in the rating opens. */
export type VoiceView = { title: string } & (
  | { voice: Voice; category: null }
  | { voice: CategoryVoice; category: RatingCategory }
);

interface Props {
  entityKey: string;
  view: VoiceView;
  onBack: () => void;
}

const SORTS: { value: CommentSort; label: string; title: string }[] = [
  { value: "score", label: "Top", title: "Most upvoted first" },
  { value: "recent", label: "Newest", title: "Most recent first" },
];

/** The exact comments behind a count, one per person. Replaces the comment
 *  list until closed; a comment deleted from Reddit has no link. Mount it
 *  with a key per place and view, so state from one never reaches another. */
export function VoiceList({ entityKey, view, onBack }: Props) {
  const [sort, setSort] = useState<CommentSort>("score");
  const { items, total, loading, error, hasMore, loadMore } = usePaged(
    `${entityKey}|${view.voice}|${view.category ?? ""}|${sort}`,
    (offset, limit, signal) => api.voices(entityKey, view.voice, view.category, sort, offset, limit, signal),
  );
  const listRef = useRef<HTMLOListElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);

  // On a phone the list sits below the analytics: let focus scroll it into view.
  useEffect(() => {
    const phone = window.matchMedia("(max-width: 760px)").matches;
    backRef.current?.focus({ preventScroll: !phone });
  }, []);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [sort]);

  return (
    <section className="cm" aria-label={view.title}>
      <div className="cm-head">
        <button type="button" className="cm-back" ref={backRef} onClick={onBack}>
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M10 3.5L5.5 8l4.5 4.5" />
          </svg>
          All comments
        </button>
        <div className="cm-sort" role="group" aria-label="Sort comments">
          {SORTS.map((s) => (
            <button key={s.value} type="button" title={s.title} aria-pressed={s.value === sort} onClick={() => setSort(s.value)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <div className="cm-sub">
        <p className="sh-eye">{view.title}</p>
      </div>
      <ol className="cm-list" ref={listRef}>
        {items.map((m) => (
          <RedditComment key={m.mention_id} mention={m} />
        ))}
        {loading && items.length === 0 && [0, 1, 2].map((i) => <li key={i} className="rc skel" aria-hidden="true" />)}
        {error && <li className="cm-err">{error}</li>}
        {!loading && !error && items.length === 0 && <li className="cm-none">No comments to show.</li>}
        {!loading && !error && items.length > 0 && (
          <li className="cm-none" aria-live="polite">
            {total.toLocaleString()} {total === 1 ? "person" : "people"}, one comment each.
          </li>
        )}
        {hasMore && (
          <li className="cm-more">
            <button type="button" className="pill-button" onClick={loadMore} disabled={loading}>
              {loading ? "Loading…" : "Load more"}
            </button>
          </li>
        )}
      </ol>
    </section>
  );
}
