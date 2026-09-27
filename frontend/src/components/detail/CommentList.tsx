import { useEffect, useRef } from "react";
import { useComments } from "../../hooks/useComments";
import { RedditComment } from "./RedditComment";
import "./CommentList.css";

interface Props {
  entityKey: string;
  onClose: () => void;
}

export function CommentList({ entityKey, onClose }: Props) {
  const { items, total, loading, error, hasMore, loadMore } = useComments(entityKey);
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [entityKey]);

  return (
    <section className="cm" aria-label="Comments">
      <div className="cm-head">
        <p className="sh-eye">{total ? `${total.toLocaleString()} ${total === 1 ? "comment" : "comments"} · Top` : "Comments"}</p>
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
