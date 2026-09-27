import { memo } from "react";
import type { Mention } from "../../api/types";
import { ago, avatarColor, redditUrl } from "../../lib/format";
import "./RedditComment.css";

interface Props {
  mention: Mention;
}

export const RedditComment = memo(function RedditComment({ mention: m }: Props) {
  const author = m.author && m.author !== "[deleted]" ? m.author : null;
  const url = m.was_deleted_later ? null : redditUrl(m.permalink);

  return (
    <li className="rc">
      <div className="rc-head">
        <span className="av" style={{ background: author ? avatarColor(author) : "var(--faint)" }} aria-hidden="true">
          {author ? author[0].toUpperCase() : "?"}
        </span>
        <b>{author ? `u/${author}` : "[deleted]"}</b>
        {m.created_utc && (
          <>
            <span aria-hidden="true">·</span>
            <time dateTime={m.created_utc}>{ago(m.created_utc)}</time>
          </>
        )}
        {m.is_negated && <span className="rc-avoid">says avoid</span>}
      </div>
      <p className="rc-body">{m.body}</p>
      <div className="rc-act">
        <span className="vote" aria-label={`${m.score ?? 0} points`}>
          <svg className="up" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 2.5l5 6H10v5H6v-5H3z" />
          </svg>
          {m.score ?? "•"}
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 13.5l5-6H10v-5H6v5H3z" />
          </svg>
        </span>
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer">
            Open on Reddit
          </a>
        ) : (
          <span className="rc-gone">deleted</span>
        )}
      </div>
      {m.thread_title && <p className="rc-sub">r/FoodNYC · {m.thread_title}</p>}
    </li>
  );
});
