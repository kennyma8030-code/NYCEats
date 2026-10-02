import { useEffect, useRef, useState } from "react";
import type { CommentSort } from "../../api/types";
import { useComments } from "../../hooks/useComments";
import { RedditComment } from "./RedditComment";
import "./CommentList.css";

interface Props {
  entityKey: string;
  onClose: () => void;
}

const SORTS: { value: CommentSort; label: string; title: string }[] = [
  { value: "score", label: "Top", title: "Most upvoted first" },
  { value: "recent", label: "Newest", title: "Most recent first" },
  { value: "oldest", label: "Oldest", title: "Oldest first" },
];

export function CommentList({ entityKey, onClose }: Props) {
  // Kept across restaurants: someone reading "Newest" wants it on the next one too.
  const [sort, setSort] = useState<CommentSort>("score");
  const { items, total, loading, error, hasMore, loadMore } = useComments(entityKey, sort);
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [entityKey, sort]);

  return (
    <section className="cm" aria-label="Comments">
      <div className="cm-head">
        <p className="sh-eye">{total ? `${total.toLocaleString()} ${total === 1 ? "comment" : "comments"}` : "Comments"}</p>
        <div className="cm-sort" role="group" aria-label="Sort comments">
          {SORTS.map((s) => (
            <button key={s.value} type="button" title={s.title} aria-pressed={s.value === sort} onClick={() => setSort(s.value)}>
              {s.label}
            </button>
          ))}
        </div>
        <button type="button" className="sh-x" aria-label="Close" onClick={onClose}>
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
          </svg>
        </button>
      </div>
      <ol className="cm-list" ref={listRef}>
        {items.map((m) => (
          <RedditComment key={m.mention_id} mention={m} />
        ))}
        {loading && items.length === 0 && [0, 1, 2].map((i) => <li key={i} className="rc skel" aria-hidden="true" />)}
        {error && <li className="cm-err">{error}</li>}
        {!loading && !error && items.length === 0 && <li className="cm-none">No comments yet.</li>}
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
