import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { api } from "../../api/client";
import type { LedgerItem, RatingCategory, RestaurantDetail } from "../../api/types";
import { useFetch } from "../../hooks/useFetch";
import { useRestaurant } from "../../hooks/useRestaurant";
import { capitalize, plural, redditUrl, titleCase, whereLine } from "../../lib/format";
import { previewTop } from "../../lib/layout";
import { CATEGORY_LABEL, isRankable, pct, people } from "../../lib/rating";
import { currentCity } from "../../state/city";
import { Icon } from "../Icon";
import { CommentsPane, type VoiceView } from "./Comments";
import "./Place.css";

interface Props {
  /** preview is the small card beside a hovered row; open is the restaurant itself. */
  mode: "preview" | "open";
  entityKey: string;
  /** The place as a list row; null while it is still being fetched. */
  item: LedgerItem | null;
  error: string | null;
  /** Whether the comments, once open, have a panel of their own; otherwise they take this one. */
  columns: boolean;
  /** Whether the comments are open. They are not until a number or "All comments" asks for them. */
  comments: boolean;
  onComments: (open: boolean) => void;
  /** In preview, where the hovered row is, so the preview can sit level with it. */
  rowTop: number;
  viewportHeight: number;
  /** A phone's sheet: its handle, and whether it is folded down. */
  grab?: ReactNode;
  peek?: boolean;
  dev: boolean;
  onOpen: () => void;
  /** Close the restaurant, or take the preview down. */
  onClose: () => void;
  /** The pointer came onto the preview, and left it. */
  onHold: () => void;
  onRelease: () => void;
}

interface Ui {
  key: string;
  voices: VoiceView | null;
  /** Counts the times a number sent the reader to the comments. */
  jumps: number;
}

/**
 * One restaurant, beside the list. It is one panel throughout: small while
 * it previews a hovered row, and the same element grown wider once the row
 * is clicked, wide enough to show everything without scrolling. Its comments
 * stay shut until they are asked for: every number here is a button that
 * opens the comments it counts, in a second panel to the right (or, where
 * there is no room for one, in place of the overview). Escape steps out one
 * level: from one number's comments to all of them, then out of the
 * comments, then from the restaurant to the list.
 */
export function PlacePanels({
  mode, entityKey, item, error, columns, comments: talking, onComments, rowTop, viewportHeight, grab, peek, dev, onOpen, onClose, onHold, onRelease,
}: Props) {
  const { data, error: detailError } = useRestaurant(entityKey);
  // What is showing belongs to one restaurant: another starts from the top.
  const [stored, setUi] = useState<Ui>({ key: entityKey, voices: null, jumps: 0 });
  const ui = stored.key === entityKey ? stored : { key: entityKey, voices: null, jumps: 0 };
  const open = mode === "open";
  const ready = item !== null;

  const panel = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const head = useRef<HTMLElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const commentScroller = useRef<HTMLDivElement>(null);
  const commentsTitle = useRef<HTMLHeadingElement>(null);

  // The preview's height is its content's, so its place is worked out once
  // that is drawn, and again when the summary arrives and makes it taller.
  const [y, setY] = useState(() => previewTop(rowTop, 300, viewportHeight));
  useLayoutEffect(() => {
    if (!open && panel.current) setY(previewTop(rowTop, panel.current.offsetHeight, viewportHeight));
  }, [open, rowTop, viewportHeight, entityKey, data]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // A menu or the search box that used the key has already said so.
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (open && talking && ui.voices) setUi({ ...ui, voices: null });
      else if (open && talking) onComments(false);
      else onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, talking, ui, onClose, onComments]);

  // Move focus to the name once there is one, so a keyboard or a screen
  // reader starts at the restaurant rather than back at the list.
  useEffect(() => {
    if (open && ready) heading.current?.focus({ preventScroll: true });
  }, [open, ready, entityKey]);

  // A number was clicked: bring the top of its comments into view and put
  // the focus on their heading.
  useEffect(() => {
    if (!ui.jumps) return;
    if (commentScroller.current) commentScroller.current.scrollTop = 0;
    else if (scroller.current && head.current) {
      scroller.current.scrollTop = Math.min(scroller.current.scrollTop, head.current.offsetTop + head.current.offsetHeight);
    }
    commentsTitle.current?.focus({ preventScroll: true });
  }, [ui.jumps]);

  const show = (voices: VoiceView | null) => {
    setUi({ key: entityKey, voices, jumps: ui.jumps + 1 });
    onComments(true);
  };
  const ask = (view: VoiceView) => () => show(view);
  const allComments = () => show(null);
  const closeComments = () => {
    onComments(false);
    heading.current?.focus({ preventScroll: true });
  };

  const comments = (
    <CommentsPane
      key={entityKey} entityKey={entityKey} view={ui.voices} dev={dev} title={commentsTitle}
      onAll={() => setUi({ ...ui, voices: null })}
    />
  );

  const name = item?.name ?? "Restaurant";
  // One <aside> in both modes, at the same place in the tree, so that
  // opening a previewed restaurant restyles the element already on screen
  // and its width, position and height can animate.
  return (
    <>
      <aside
        ref={panel} className={`panel place-panel ${mode}${peek ? " peek" : ""}`}
        style={open ? undefined : ({ "--y": `${y}px` } as CSSProperties)}
        aria-label={open ? name : `Preview of ${name}`}
        onPointerEnter={open ? undefined : onHold} onPointerLeave={open ? undefined : onRelease}
      >
        {!open && item && <Preview item={item} data={data} failed={!!detailError} onOpen={onOpen} />}
        {open && grab}
        {open && (
        <div className="panel-scroll" ref={scroller}>
          <article className="place">
            <button type="button" className="back" onClick={onClose}>
              <Icon name="left" />
              Full list
            </button>
            {!item ? (
              error ? (
                <div className="board-msg" role="alert">
                  <p>This restaurant could not be loaded.</p>
                  <p className="board-msg-sub">{error}</p>
                </div>
              ) : (
                <div aria-busy="true" className="place-loading">
                  <span className="skel" style={{ height: 44, width: "70%" }} />
                  <span className="skel" style={{ height: 14, width: "40%" }} />
                  <span className="skel" style={{ height: 120 }} />
                </div>
              )
            ) : (
              <>
                <Head item={item} data={data} heading={heading} head={head} ask={ask} />
                {/* The overview stays mounted under the comments, so going back finds it as it was left. */}
                <div hidden={talking && !columns}>
                  <About item={item} data={data} failed={!!detailError} ask={ask} allComments={allComments} />
                </div>
                {talking && !columns && (
                  <>
                    <button type="button" className="back place-overview" onClick={closeComments}>
                      <Icon name="left" />
                      Overview
                    </button>
                    {comments}
                  </>
                )}
              </>
            )}
          </article>
        </div>
        )}
      </aside>
      {open && talking && columns && item && (
        <aside className="panel comments-panel" aria-label={`Comments on ${name}`}>
          <button type="button" className="comments-close" aria-label="Close the comments" onClick={closeComments}>
            <Icon name="close" />
          </button>
          <div className="panel-scroll" ref={commentScroller}>{comments}</div>
        </aside>
      )}
    </>
  );
}

const dishNames = (data: RestaurantDetail | null, count: number) => data?.top_dishes.slice(0, count).map((d) => capitalize(d.name)) ?? [];

interface PreviewProps {
  item: LedgerItem;
  data: RestaurantDetail | null;
  failed: boolean;
  onOpen: () => void;
}

/** A hovered row at a glance, and no more than that: who, where, how liked,
 *  the gist, and what to order. The whole card opens the restaurant. It is
 *  out of the tab order because the row it belongs to already does the same. */
function Preview({ item, data, failed, onOpen }: PreviewProps) {
  const r = item.rating ?? null;
  const where = whereLine(item.cuisine, item.neighborhood ?? item.borough);
  const summary = data?.place_summary?.text ?? null;
  const dishes = dishNames(data, 3);
  return (
    <button type="button" className="preview-card" tabIndex={-1} onClick={onOpen}>
      <span className="preview-head">
        <span className="preview-id">
          <span className="preview-name">{item.name}</span>
          {where && <span className="preview-where">{where}</span>}
        </span>
        {isRankable(r) && r && (
          <span className="preview-score">
            <b>{pct(r.pct_pos!)}%</b>
            <small>{plural(people(r), "person", "people")}</small>
          </span>
        )}
      </span>
      {summary && <span className="preview-summary">{summary}</span>}
      {!data && !failed && (
        <span className="preview-loading" aria-hidden="true">
          <span className="skel" />
          <span className="skel" />
        </span>
      )}
      {dishes.length > 0 && (
        <span className="preview-dishes">
          <span className="eyebrow">What people order</span>
          {dishes.map((d) => <span key={d}>{d}</span>)}
        </span>
      )}
    </button>
  );
}

type Ask = (view: VoiceView) => () => void;

interface HeadProps {
  item: LedgerItem;
  data: RestaurantDetail | null;
  heading: React.RefObject<HTMLHeadingElement>;
  head: React.RefObject<HTMLElement>;
  ask: Ask;
}

/** What and where in a line of small capitals, then the name beside the
 *  one score, with the people behind that score in small type under it. */
function Head({ item, data, heading, head, ask }: HeadProps) {
  const r = item.rating ?? null;
  const ranked = isRankable(r);
  const area = item.neighborhood ?? item.borough;
  const at = data?.locations?.[0] ?? item.location ?? null;
  const address = at?.address ? `${titleCase(at.address)}${at.borough ? `, ${at.borough}` : ""}` : null;
  const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    [item.name, address ?? area].filter(Boolean).join(", "),
  )}`;
  const opinions = ask({ title: "Positive and negative", voice: "opinions", category: null });
  return (
    <header className="place-head" ref={head}>
      {(item.cuisine || area) && (
        <p className="place-kicker">
          <span className="place-cuisine">{item.cuisine}</span>
          <span>{area}</span>
        </p>
      )}
      <div className="place-title">
        <div className="place-title-id">
          <h2 className="place-name" tabIndex={-1} ref={heading}>{item.name}</h2>
          <a className="place-pin" href={mapUrl} target="_blank" rel="noopener noreferrer" aria-label={`${item.name} on Google Maps`}>
            <svg aria-hidden="true" width="30" height="30" viewBox="0 0 24 24" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
              <circle cx="12" cy="10" r="2.5" />
            </svg>
          </a>
        </div>
        {ranked && r && (
          <button
            type="button" className="place-score" onClick={opinions}
            aria-label={`${pct(r.pct_pos!)}% positive, ${plural(people(r), "person", "people")}. Show their comments`}
          >
            {pct(r.pct_pos!)}%
            <small>{r.pos.toLocaleString()} of {people(r).toLocaleString()} recommend</small>
          </button>
        )}
      </div>
      {!ranked && (
        <p className="place-quiet">
          Not enough opinions yet to rate it.
          {r && people(r) > 0 && (
            <>
              {" "}
              <button type="button" className="textlink" onClick={opinions}>Read what people said</button>
            </>
          )}
        </p>
      )}
    </header>
  );
}

// How long one comment stays up in the quote card before the next.
const TURN_MS = 5000;

/** The most upvoted comments, one at a time, each turning to the next with a
 *  flash of colour. Pointing at the card or focusing inside it holds the one
 *  showing. Its author links to Reddit only while the comment is still there. */
function QuoteCard({ entityKey, onAll }: { entityKey: string; onAll: () => void }) {
  const city = currentCity();
  const { data } = useFetch(`${city}|${entityKey}|quotes`, (signal) => api.mentions(entityKey, "score", 0, 3, signal));
  const [turn, setTurn] = useState(0);
  const [held, setHeld] = useState(false);
  const quotes = (data?.items ?? []).filter((m) => (m.body ?? "").trim());
  const count = quotes.length;

  useEffect(() => {
    if (held || count < 2) return;
    const timer = setInterval(() => setTurn((t) => t + 1), TURN_MS);
    return () => clearInterval(timer);
  }, [held, count]);

  if (!data || count === 0) return null;
  const m = quotes[turn % count];
  const author = m.author && m.author !== "[deleted]" ? `u/${m.author}` : "[deleted]";
  const url = m.was_deleted_later ? null : redditUrl(m.permalink);
  return (
    <section
      // A new key restarts the flash for each comment.
      key={turn} className={turn ? "quote flash" : "quote"} aria-label="A top comment"
      onPointerEnter={() => setHeld(true)} onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)} onBlur={() => setHeld(false)}
    >
      <span className="quote-src">r/{city}</span>
      <p className="quote-text">{(m.body ?? "").trim()}</p>
      <div className="quote-foot">
        <p className="quote-by">
          {m.score != null && (
            <span className="quote-votes" aria-label={plural(m.score, "upvote", "upvotes")}>
              <Icon name="up" size={14} stroke={2.8} />
              {m.score.toLocaleString()}
            </span>
          )}
          {url ? <a href={url} target="_blank" rel="noopener noreferrer">{author}</a> : <span>{author}</span>}
        </p>
        <button type="button" className="redpill" onClick={onAll}>
          All {plural(data.total, "comment", "comments")}
        </button>
      </div>
    </section>
  );
}

interface AboutProps {
  item: LedgerItem;
  data: RestaurantDetail | null;
  failed: boolean;
  ask: Ask;
  allComments: () => void;
}

/** The boxes under the header, each with its label on its top edge: the
 *  summary, the five things a place is rated on, a top comment, and what to
 *  order. */
function About({ item, data, failed, ask, allComments }: AboutProps) {
  const r = item.rating ?? null;
  const summary = data?.place_summary?.text ? data.place_summary : null;
  const dishes = dishNames(data, 6);
  const hasComplaints = !!r && r.neg > 0;

  if (!data && !failed) {
    return (
      <div className="place-body" aria-busy="true">
        <span className="skel" style={{ height: 120 }} />
        <span className="skel" style={{ height: 180 }} />
      </div>
    );
  }

  return (
    <div className="place-body">
      {summary && (
        <section className="box" aria-label="Summary of the comments">
          <h3 className="box-label">Summary</h3>
          <p className="place-summary">{summary.text}</p>
        </section>
      )}

      {r && (
        <section className="box">
          <h3 className="box-label">Rated</h3>
          {/* Always the same five rows, so a place with little said about it
              shows what is missing rather than a shorter list. */}
          <ul className="rated">
            {(Object.keys(CATEGORY_LABEL) as RatingCategory[]).map((key) => {
              const c = r.categories[key];
              const label = CATEGORY_LABEL[key];
              if (!c || !c.rankable || c.pct_pos == null) {
                return (
                  <li key={key} className="rated-row off">
                    <span>{label}</span>
                    <span className="meter" aria-hidden="true" />
                    <span className="rated-num">N/A</span>
                  </li>
                );
              }
              const share = pct(c.pct_pos);
              return (
                <li key={key}>
                  <button
                    type="button" className="rated-row"
                    aria-label={`${label}: ${share}% positive, ${plural(people(c), "person", "people")}. Show their comments`}
                    onClick={ask({ title: `${label}: positive and negative`, voice: "opinions", category: key })}
                  >
                    <span>{label}</span>
                    <span className="meter" aria-hidden="true"><i style={{ width: `${share}%` }} /></span>
                    <span className="rated-num">{share}%</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {hasComplaints && (
            <button type="button" className="textlink place-quiet place-all" onClick={ask({ title: "Complaints", voice: "neg", category: null })}>
              Read the complaints
            </button>
          )}
        </section>
      )}

      <QuoteCard key={item.entity_key} entityKey={item.entity_key} onAll={allComments} />

      {dishes.length > 0 && (
        <section className="box">
          <h3 className="box-label">Order</h3>
          <ul className="dishes">
            {dishes.map((d) => <li key={d}>{d}</li>)}
          </ul>
        </section>
      )}

      {!summary && !r && dishes.length === 0 && (
        <p className="place-quiet place-empty">
          Nothing has been summarised for this place yet.{" "}
          <button type="button" className="textlink" onClick={allComments}>Read the comments</button>
        </p>
      )}
    </div>
  );
}
