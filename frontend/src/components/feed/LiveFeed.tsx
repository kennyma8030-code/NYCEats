import { useEffect, useRef, useState } from "react";
import { useFeed } from "../../hooks/useFeed";
import { RedditComment } from "../detail/RedditComment";
import "../detail/CommentList.css";
import "../ledger/LedgerList.css";
import "../rail/SearchBox.css";
import "./LiveFeed.css";

interface Props {
  onOpen: (key: string) => void;
}

/** Every post and comment on the subreddit as it comes in, with a search over them. */
export function LiveFeed({ onOpen }: Props) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [placesOnly, setPlacesOnly] = useState(false);
  const { items, fresh, loading, error, hasMore, loadMore, showFresh } = useFeed(q, placesOnly);
  // Comments that just slid in, so they can be marked for a moment.
  const [justIn, setJustIn] = useState<Set<string>>(new Set());
  const top = useRef<HTMLDivElement>(null);

  // Search after a pause in typing, not on every keystroke.
  useEffect(() => {
    const t = text.trim();
    if (t === q) return;
    const id = setTimeout(() => setQ(t), 350);
    return () => clearTimeout(id);
  }, [text, q]);

  const take = () => {
    setJustIn(new Set(fresh.map((c) => c.id)));
    showFresh();
  };

  // Someone at the top sees new comments arrive; someone reading further
  // down gets a button instead, so the list does not move under them.
  useEffect(() => {
    if (fresh.length && window.scrollY < 80) take();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fresh.length]);

  return (
    <main className="ledger stream">
      <div ref={top}>
        <h1>
          <em>Live</em> on r/FoodNYC
        </h1>
        <p className="sum">Every post and comment, newest first. New ones arrive about every 30 minutes.</p>
      </div>

      <div className="st-tools">
        <div className="sb-field st-search">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" />
            <path d="M10.5 10.5L14 14" />
          </svg>
          <input
            type="search"
            aria-label="Search posts and comments"
            placeholder="Search posts and comments…"
            autoComplete="off"
            spellCheck={false}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setQ(text.trim());
              if (e.key === "Escape") setText("");
            }}
          />
        </div>
        <button type="button" className="st-only" aria-pressed={placesOnly} onClick={() => setPlacesOnly((v) => !v)}>
          Only comments about restaurants
        </button>
      </div>

      {fresh.length > 0 && (
        <button
          type="button"
          className="st-fresh"
          onClick={() => {
            take();
            top.current?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          ↑ {fresh.length} new
        </button>
      )}

      <ol className="st-list">
        {items.map((c) => (
          <RedditComment
            key={c.id}
            mention={c.kind === "comment" ? { ...c, thread_title: c.title } : { ...c, thread_title: null }}
            post={c.kind === "post" ? { title: c.title, comments: c.num_comments } : undefined}
            places={c.places}
            onPlace={onOpen}
            className={justIn.has(c.id) ? "rc-new" : undefined}
          />
        ))}
        {loading && items.length === 0 && [0, 1, 2, 3].map((i) => <li key={i} className="rc skel" aria-hidden="true" />)}
        {error && <li className="cm-err">{error}</li>}
        {!loading && !error && items.length === 0 && (
          <li className="cm-none">{q ? `Nothing mentions “${q}”.` : "Nothing yet."}</li>
        )}
        {hasMore && (
          <li className="cm-more">
            <button type="button" className="pill-button" onClick={loadMore} disabled={loading}>
              {loading ? "Loading…" : "Load more"}
            </button>
          </li>
        )}
      </ol>
    </main>
  );
}
