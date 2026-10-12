import { memo } from "react";
import type { FeedPlace, Mention } from "../../api/types";
import { ago, avatarColor, redditUrl } from "../../lib/format";
import "./RedditComment.css";

/** What a card shows: a restaurant's mention, or a comment from the live stream. */
type CommentLike = Pick<Mention, "author" | "score" | "created_utc" | "body" | "permalink" | "was_deleted_later" | "thread_title"> & {
  is_negated?: boolean;
};

interface Props {
  mention: CommentLike;
  /** A post rather than a comment: its title, and how many comments it has. */
  post?: { title: string | null; comments: number | null };
  /** The restaurants it mentions, as links to open them (stream only). */
  places?: FeedPlace[];
  onPlace?: (key: string) => void;
  className?: string;
}

export const RedditComment = memo(function RedditComment({ mention: m, post, places, onPlace, className }: Props) {
  const author = m.author && m.author !== "[deleted]" ? m.author : null;
  const url = m.was_deleted_later ? null : redditUrl(m.permalink);

  return (
    <li className={className ? `rc ${className}` : "rc"}>
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
        {post && <span className="rc-kind">Post</span>}
      </div>
      {post?.title && <p className="rc-title">{post.title}</p>}
      {m.body && <p className={post ? "rc-body rc-clamp" : "rc-body"}>{m.body}</p>}
      {places && places.length > 0 && (
        <div className="rc-places">
          {places.map((p) => (
            <button key={p.key} type="button" onClick={() => onPlace?.(p.key)}>
              {p.name}
            </button>
          ))}
        </div>
      )}
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
        {post?.comments != null && (
          <span className="rc-count">
            {post.comments.toLocaleString()} {post.comments === 1 ? "comment" : "comments"}
          </span>
        )}
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer">
            Open on Reddit
          </a>
        ) : (
          <span className="rc-gone">deleted</span>
        )}
      </div>
      {!post && m.thread_title && <p className="rc-sub">r/FoodNYC · {m.thread_title}</p>}
    </li>
  );
});
