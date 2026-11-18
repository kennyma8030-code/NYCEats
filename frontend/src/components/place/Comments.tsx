import { memo, useState, type RefObject } from "react";
import { api } from "../../api/client";
import type { CategoryVoice, CommentSort, Mention, RatingCategory, Voice } from "../../api/types";
import { usePaged } from "../../hooks/usePaged";
import { ago, plural, redditUrl } from "../../lib/format";
import { currentCity } from "../../state/city";
import { Icon } from "../Icon";
import { ExtractionView } from "./ExtractionView";

/** Which comments a number in the rating opens. */
export type VoiceView = { title: string } & (
  | { voice: Voice; category: null }
  | { voice: CategoryVoice; category: RatingCategory }
);

const SORTS: { value: CommentSort; label: string; title: string }[] = [
  { value: "score", label: "Top", title: "Most upvoted first" },
  { value: "recent", label: "Newest", title: "Most recent first" },
  { value: "oldest", label: "Oldest", title: "Oldest first" },
];

// Past this a comment is folded, so one long story does not bury the rest.
const FOLD = 420;

interface CardProps {
  mention: Mention;
  /** Offer the extractor's reading of the comment: a debugging aid, behind ?dev=1. */
  dev?: boolean;
}

/** One Reddit comment as evidence. It links to Reddit only while the comment
 *  is still there: one deleted since has no link, and says so. */
export const CommentCard = memo(function CommentCard({ mention: m, dev }: CardProps) {
  const [whole, setWhole] = useState(false);
  const [extraction, setExtraction] = useState(false);
  const author = m.author && m.author !== "[deleted]" ? `u/${m.author}` : "[deleted]";
  const url = m.was_deleted_later ? null : redditUrl(m.permalink);
  const body = (m.body ?? "").trim();
  const long = body.length > FOLD;

  return (
    <li className="cmt">
      <p className="cmt-meta">
        <span className="cmt-who">{author}</span>
        {m.created_utc && <time dateTime={m.created_utc}>{ago(m.created_utc)}</time>}
        {m.is_negated && <span className="cmt-avoid">says avoid</span>}
      </p>
      {extraction ? (
        <ExtractionView itemId={m.comment_id} />
      ) : (
        <p className="cmt-body">
          {long && !whole ? `${body.slice(0, FOLD).trimEnd()}… ` : body}
          {long && !whole && (
            <button type="button" className="textlink" onClick={() => setWhole(true)}>Read all</button>
          )}
        </p>
      )}
      {m.thread_title && <p className="cmt-thread">In “{m.thread_title}”</p>}
      <p className="cmt-meta">
        {m.score != null && (
          <span className="cmt-score" aria-label={plural(m.score, "upvote", "upvotes")}>
            <Icon name="up" size={12} stroke={2.6} />
            {m.score.toLocaleString()}
          </span>
        )}
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer">Open on Reddit</a>
        ) : (
          <span>Deleted from Reddit</span>
        )}
        {dev && (
          <button type="button" className="textlink" aria-pressed={extraction} onClick={() => setExtraction((v) => !v)}>
            {extraction ? "Text" : "Extraction"}
          </button>
        )}
      </p>
    </li>
  );
});

function SortTabs({ sorts, value, onChange }: { sorts: typeof SORTS; value: CommentSort; onChange: (s: CommentSort) => void }) {
  return (
    <div className="minitabs" role="group" aria-label="Sort comments">
      {sorts.map((s) => (
        <button key={s.value} type="button" title={s.title} aria-pressed={s.value === value} onClick={() => onChange(s.value)}>
          {s.label}
        </button>
      ))}
    </div>
  );
}

interface ListProps<T> {
  paged: ReturnType<typeof usePaged<T>>;
  empty: string;
  children: (item: T) => React.ReactNode;
}

function PagedList<T>({ paged, empty, children }: ListProps<T>) {
  const { items, loading, error, hasMore, loadMore, total } = paged;
  return (
    <>
      <ol className="cmts">
        {items.map(children)}
        {loading && items.length === 0 && [0, 1, 2].map((i) => <li key={i} className="cmt-skel skel" aria-hidden="true" />)}
      </ol>
      {error && <p className="place-quiet" role="alert">The comments could not be loaded: {error}</p>}
      {!loading && !error && items.length === 0 && <p className="place-quiet">{empty}</p>}
      {hasMore && (
        <button type="button" className="pill cmts-more" onClick={loadMore} disabled={loading}>
          {loading ? "Loading…" : `Show more (${(total - items.length).toLocaleString()} left)`}
        </button>
      )}
    </>
  );
}

interface PaneProps {
  entityKey: string;
  /** The comments behind one number; null lists every comment. */
  view: VoiceView | null;
  dev: boolean;
  /** Back from one number's comments to all of them. */
  onAll: () => void;
  /** The pane's heading, which takes the focus when a number opens it. */
  title: RefObject<HTMLHeadingElement>;
}

/** A restaurant's comments, as a panel of their own or a tab of the
 *  restaurant's: all of them, or the ones behind the number that was
 *  clicked. */
export function CommentsPane({ entityKey, view, dev, onAll, title }: PaneProps) {
  return (
    <section className="cpane" aria-label="Comments">
      {view ? (
        <VoiceComments key={`${view.voice}|${view.category}`} entityKey={entityKey} view={view} dev={dev} onAll={onAll} title={title} />
      ) : (
        <AllComments entityKey={entityKey} dev={dev} title={title} />
      )}
    </section>
  );
}

/** Every comment that mentions the place, a few at a time, in the order chosen. */
function AllComments({ entityKey, dev, title }: Pick<PaneProps, "entityKey" | "dev" | "title">) {
  const [sort, setSort] = useState<CommentSort>("score");
  const paged = usePaged(
    `${currentCity()}|${entityKey}|${sort}`,
    (offset, limit, signal) => api.mentions(entityKey, sort, offset, limit, signal),
    10,
  );
  return (
    <>
      <div className="cpane-head">
        <h3 className="cpane-title" tabIndex={-1} ref={title}>
          {paged.total ? plural(paged.total, "comment", "comments") : "Comments"}
        </h3>
        <SortTabs sorts={SORTS} value={sort} onChange={setSort} />
      </div>
      <PagedList paged={paged} empty="No comments yet.">
        {(m: Mention) => <CommentCard key={m.mention_id} mention={m} dev={dev} />}
      </PagedList>
    </>
  );
}

/** The exact comments behind one number of the rating, one per person, so
 *  the list is as long as the number that opened it. */
function VoiceComments({ entityKey, view, dev, onAll, title }: PaneProps & { view: VoiceView }) {
  const [sort, setSort] = useState<CommentSort>("score");
  const paged = usePaged(
    `${currentCity()}|${entityKey}|${view.voice}|${view.category ?? ""}|${sort}`,
    (offset, limit, signal) => api.voices(entityKey, view.voice, view.category, sort, offset, limit, signal),
    20,
  );
  return (
    <>
      <button type="button" className="back cpane-back" onClick={onAll}>
        <Icon name="left" />
        All comments
      </button>
      <div className="cpane-head">
        <div>
          <h3 className="cpane-title" tabIndex={-1} ref={title}>{view.title}</h3>
          <p className="place-quiet">
            {paged.total ? `${plural(paged.total, "person", "people")}, one comment each` : " "}
          </p>
        </div>
        <SortTabs sorts={SORTS.slice(0, 2)} value={sort} onChange={setSort} />
      </div>
      <PagedList paged={paged} empty="No comments to show.">
        {(m: Mention) => <CommentCard key={m.mention_id} mention={m} dev={dev} />}
      </PagedList>
    </>
  );
}
