import { useEffect, useRef, useState } from "react";
import type { CommentSort, RatingCategory, Voice } from "../../api/types";
import { useVoices } from "../../hooks/useVoices";
import { RedditComment } from "./RedditComment";
import "./CommentList.css";

/** Which comments a number in the rating opens: one or more voices, so the
 *  headline can offer positive and negative side by side. */
export interface VoiceView {
  title: string;
  category: RatingCategory | null;
  tabs: { voice: Voice; label: string; count: number }[];
  /** The tab shown first. */
  start: Voice;
}

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
 *  list until closed; a comment deleted from Reddit has no link. */
export function VoiceList({ entityKey, view, onBack }: Props) {
  const [voice, setVoice] = useState<Voice>(view.start);
  const [sort, setSort] = useState<CommentSort>("score");
  const { items, total, loading, error, hasMore, loadMore } = useVoices(entityKey, voice, view.category, sort);
  const listRef = useRef<HTMLOListElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);

  // A different number was clicked: start on its own tab.
  useEffect(() => setVoice(view.start), [view]);
  useEffect(() => backRef.current?.focus({ preventScroll: true }), [view]);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [voice, sort, view]);

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
        {view.tabs.length > 1 && (
          <div className="cm-sort" role="group" aria-label="Kind of comment">
            {view.tabs.map((t) => (
              <button key={t.voice} type="button" aria-pressed={t.voice === voice} onClick={() => setVoice(t.voice)}>
                {t.label} {t.count.toLocaleString()}
              </button>
            ))}
          </div>
        )}
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
