import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { LedgerItem, RestaurantDetail } from "../../api/types";
import { useRestaurant } from "../../hooks/useRestaurant";
import { capitalize, monthYear, plural, titleCase, whereLine } from "../../lib/format";
import { previewTop } from "../../lib/layout";
import { goodToKnow, isRankable, pct, people, type Verdict } from "../../lib/rating";
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
  /** Whether the comments have a panel of their own; otherwise they are a tab in this one. */
  columns: boolean;
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

type Tab = "about" | "comments";

interface Ui {
  key: string;
  voices: VoiceView | null;
  tab: Tab;
  /** Counts the times a number sent the reader to the comments. */
  jumps: number;
}

/**
 * One restaurant, beside the list. It is one panel throughout: small while
 * it previews a hovered row, and the same element grown wider once the row
 * is clicked, with the comments in a second panel to its right (or, where
 * there is no room for one, in a tab). Every number here is a button that
 * shows the comments it counts. Escape steps out one level: from one
 * number's comments to all of them, then from the restaurant to the list.
 */
export function PlacePanels({
  mode, entityKey, item, error, columns, rowTop, viewportHeight, grab, peek, dev, onOpen, onClose, onHold, onRelease,
}: Props) {
  const { data, error: detailError } = useRestaurant(entityKey);
  // What is showing belongs to one restaurant: another starts from the top.
  const [stored, setUi] = useState<Ui>({ key: entityKey, voices: null, tab: "about", jumps: 0 });
  const ui = stored.key === entityKey ? stored : { key: entityKey, voices: null, tab: "about" as Tab, jumps: 0 };
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
      if (open && ui.voices) setUi({ ...ui, voices: null });
      else onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, ui, onClose]);

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

  const ask = (view: VoiceView) => () => setUi({ key: entityKey, voices: view, tab: "comments", jumps: ui.jumps + 1 });
  const allComments = () => setUi({ key: entityKey, voices: null, tab: "comments", jumps: ui.jumps + 1 });

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
                {columns ? (
                  <About item={item} data={data} failed={!!detailError} ask={ask} allComments={allComments} />
                ) : (
                  <>
                    <div className="place-tabs" role="tablist" aria-label={name}>
                      {(["about", "comments"] as Tab[]).map((t) => (
                        <button
                          key={t} type="button" role="tab" id={`place-tab-${t}`} aria-selected={ui.tab === t}
                          aria-controls={`place-pane-${t}`} onClick={() => setUi({ ...ui, tab: t })}
                        >
                          {t === "about" ? "Overview" : "Comments"}
                        </button>
                      ))}
                    </div>
                    {/* Both stay mounted, so going back to a tab finds it as it was left. */}
                    <div role="tabpanel" id="place-pane-about" aria-labelledby="place-tab-about" hidden={ui.tab !== "about"}>
                      <About item={item} data={data} failed={!!detailError} ask={ask} allComments={allComments} />
                    </div>
                    <div role="tabpanel" id="place-pane-comments" aria-labelledby="place-tab-comments" hidden={ui.tab !== "comments"}>
                      {comments}
                    </div>
                  </>
                )}
              </>
            )}
          </article>
        </div>
        )}
      </aside>
      {open && columns && item && (
        <aside className="panel comments-panel" aria-label={`Comments on ${name}`}>
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

/** Who and where on the left, the one score on the right. */
function Head({ item, data, heading, head, ask }: HeadProps) {
  const r = item.rating ?? null;
  const ranked = isRankable(r);
  const where = whereLine(item.cuisine, item.neighborhood ?? item.borough);
  const at = data?.locations?.[0] ?? item.location ?? null;
  const more = (data?.locations?.length ?? item.location_count ?? 0) - 1;
  const opinions = ask({ title: "Positive and negative", voice: "opinions", category: null });
  return (
    <header className="place-head" ref={head}>
      <div className="place-id">
        <h2 className="place-name" tabIndex={-1} ref={heading}>{item.name}</h2>
        {where && <p className="place-what">{where}</p>}
        {at?.address && (
          <p className="place-where">
            {titleCase(at.address)}{at.borough ? `, ${at.borough}` : ""}
            {more > 0 ? `, and ${plural(more, "more location", "more locations")}` : ""}
          </p>
        )}
        {!ranked && (
          <p className="place-where">
            Not enough opinions yet to rate it.
            {r && people(r) > 0 && (
              <>
                {" "}
                <button type="button" className="textlink" onClick={opinions}>Read what people said</button>
              </>
            )}
          </p>
        )}
      </div>
      {ranked && r && (
        <button
          type="button" className="place-score" onClick={opinions}
          aria-label={`${pct(r.pct_pos!)}% positive, ${plural(people(r), "person", "people")}. Show their comments`}
        >
          <b>{pct(r.pct_pos!)}%</b>
          <small>{plural(people(r), "person", "people")}</small>
        </button>
      )}
    </header>
  );
}

interface AboutProps {
  item: LedgerItem;
  data: RestaurantDetail | null;
  failed: boolean;
  ask: Ask;
  allComments: () => void;
}

/** The sections under the header, each ruled off and labelled: the summary,
 *  what to order, and what the place is liked and faulted for. */
function About({ item, data, failed, ask, allComments }: AboutProps) {
  const r = item.rating ?? null;
  const summary = data?.place_summary?.text ? data.place_summary : null;
  const dishes = dishNames(data, 6);
  const know = r && isRankable(r) ? goodToKnow(r) : { liked: [], complaints: [] };
  const hasComplaints = !!r && r.neg > 0;
  const written = summary ? monthYear(summary.written_at) : "";

  if (!data && !failed) {
    return (
      <div className="place-sec" aria-busy="true">
        <span className="skel" style={{ height: 12, width: 120 }} />
        <span className="skel" style={{ height: 96 }} />
      </div>
    );
  }

  const row = (v: Verdict, side: "positive" | "negative") => (
    <li key={v.key}>
      <button
        type="button" className="know-row"
        aria-label={`${v.label}: ${v.pct}% ${side}. Show the comments`}
        onClick={ask(side === "positive"
          ? { title: `${v.label}: what people liked`, voice: "pos", category: v.key }
          : { title: `${v.label}: complaints`, voice: "neg", category: v.key })}
      >
        <span>{v.label}</span>
        <span className="know-num"><b>{v.pct}%</b> {side}</span>
      </button>
    </li>
  );

  return (
    <>
      {summary && (
        <section className="place-sec" aria-label="Summary of the comments">
          <h3 className="eyebrow">What people say</h3>
          <p className="place-summary">{summary.text}</p>
          <p className="place-quiet">
            Summary of{" "}
            <button type="button" className="textlink" onClick={allComments}>
              {summary.comment_count ? plural(summary.comment_count, "comment", "comments") : "the comments"}
            </button>
            {written ? `, updated ${written}` : ""}
          </p>
        </section>
      )}

      {dishes.length > 0 && (
        <section className="place-sec">
          <h3 className="eyebrow">What people order</h3>
          <ul className="dishes">
            {dishes.map((d) => <li key={d}>{d}</li>)}
          </ul>
        </section>
      )}

      {(know.liked.length > 0 || know.complaints.length > 0 || hasComplaints) && (
        <section className="place-sec">
          <h3 className="eyebrow">Good to know</h3>
          {(know.liked.length > 0 || know.complaints.length > 0) && (
            <div className={know.liked.length > 0 && know.complaints.length > 0 ? "know" : "know one"}>
              {know.liked.length > 0 && (
                <div>
                  <p className="know-label">People like</p>
                  <ul>{know.liked.map((v) => row(v, "positive"))}</ul>
                </div>
              )}
              {know.complaints.length > 0 && (
                <div>
                  <p className="know-label">People complain about</p>
                  <ul>{know.complaints.map((v) => row(v, "negative"))}</ul>
                </div>
              )}
            </div>
          )}
          {hasComplaints && (
            <button type="button" className="textlink place-all" onClick={ask({ title: "Complaints", voice: "neg", category: null })}>
              Read the complaints
            </button>
          )}
        </section>
      )}

      {!summary && dishes.length === 0 && know.liked.length === 0 && know.complaints.length === 0 && !hasComplaints && (
        <section className="place-sec">
          <p className="place-quiet">
            Nothing has been summarised for this place yet.{" "}
            <button type="button" className="textlink" onClick={allComments}>Read the comments</button>
          </p>
        </section>
      )}
    </>
  );
}
