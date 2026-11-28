import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { SearchFilter, SearchItem, SearchMatched, SearchResponse } from "../../api/types";
import { useFetch } from "../../hooks/useFetch";
import type { RowHover } from "../../hooks/useHoverPreview";
import { plural } from "../../lib/format";
import { afterIds, afterPage, countedBy, loaded, moreLabel, nextRequest, resultId, seenCount, type Loaded } from "../../lib/results";
import { CommentCard } from "../place/Comments";
import "./SearchResults.css";

interface Props {
  query: string;
  /** The city searched. In the request's key so one city's answer never
   *  stands under another's name. */
  city: string;
  dev: boolean;
  /** Beside an open restaurant: only the names, still in the answer's order. */
  compact?: boolean;
  /** The row to light: the pointer is on it or on its pin. */
  hot: string | null;
  onHot: (key: string | null) => void;
  /** The open restaurant, lit and marked as the current one. */
  selected: string | null;
  /** Opens a preview beside a row the pointer rests on. */
  hover: RowHover;
  onOpen: (key: string) => void;
  onClose: () => void;
}

function Part({ f, out }: { f: SearchFilter; out?: boolean }) {
  return (
    <span className={out ? "sr-part out" : "sr-part"}>
      <i>{out ? "not" : f.type}</i>
      {f.value}
    </span>
  );
}

/**
 * Places for a typed query, in the city's panel where its ranking would be:
 * each with the count it is ranked by and the comments behind that count.
 *
 * Two requests, so nothing waits on a model: the fast answer is read from
 * the site's own vocabulary and shows at once. Only when it says the query
 * held words it could not explain is the full one asked for, and it replaces
 * the fast one when it lands. If the full one fails, the fast one stays,
 * with the server's own note that its words were matched as typed.
 *
 * The number beside a place is a count of comments' authors, and every one
 * of those comments can be opened here: the first few come with the answer
 * and the rest are a button away (Evidence).
 */
export function SearchResults({ query, city, dev, compact = false, hot, onHot, selected, hover, onOpen, onClose }: Props) {
  const fast = useFetch<SearchResponse>(`${city}|fast|${query}`, (signal) => api.search(query, "fast", signal));
  // useFetch keeps the last answer while the next loads; only the answer to
  // this query may be shown under it.
  const quick = fast.current ? fast.data : null;
  const wantFull = quick?.needs_model === true;
  const full = useFetch<SearchResponse>(wantFull ? `${city}|full|${query}` : null, (signal) => api.search(query, "full", signal));

  const data = (full.current ? full.data : null) ?? quick;
  const reading = wantFull && full.loading;
  const parse = data?.parse;
  const byMeaning = data?.ranked_by === "matching_people";

  return (
    <div className="sr-panel">
      {!compact && <div className="sr-head">
        <div className="sr-title">
          <h2>“{query}”</h2>
          <button type="button" className="textlink" onClick={onClose}>Clear search</button>
        </div>
        <p className="sr-sum">
          {fast.loading && !data
            ? "Searching…"
            : data
              ? `${plural(data.total, "place", "places")}, by how many people ${countedBy(data)}.`
              : ""}
          {reading && " Reading the query more closely…"}
        </p>
        {parse && (parse.search_text || parse.include.length > 0 || parse.exclude.length > 0) && (
          <p className="sr-parts">
            {parse.search_text && (
              <span className="sr-part">
                <i>about</i>
                {parse.search_text}
              </span>
            )}
            {parse.include.map((f) => <Part key={`in:${f.type}:${f.value}`} f={f} />)}
            {parse.exclude.map((f) => <Part key={`out:${f.type}:${f.value}`} f={f} out />)}
          </p>
        )}
        {data?.notes.map((n) => <p key={n} className="sr-note">{n}</p>)}
      </div>}

      {fast.error ? (
        <div className="board-msg" role="alert">
          <p>This search could not be run.</p>
          <p className="board-msg-sub">{fast.error}</p>
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="board-msg">
          <p>Nothing matches this search.</p>
          <button type="button" className="pill" onClick={onClose}>Back to the list</button>
        </div>
      ) : (
        <ol className={reading ? "rows busy" : "rows"} aria-busy={fast.loading || reading} onScroll={hover.follow}>
          {/* Placeholders only while the answer is on its way; a failure or an empty answer is said above. */}
          {!data && Array.from({ length: 6 }, (_, i) => <li key={i} className="row-skel skel" aria-hidden="true" />)}
          {data?.items.map((it) => {
            const area = it.neighborhood ?? it.borough;
            const key = it.entity_key;
            return (
              <li key={key} className="sr-item">
                {/* Lit, marked and previewed exactly as a row of the ranking
                    is (Row in Leaderboard.tsx): a finger has no hover, and
                    only focus that came from the keyboard opens a preview. */}
                <button
                  type="button" className={hot === key || selected === key ? "row on" : "row"} data-key={key}
                  aria-current={selected === key ? "true" : undefined} title={compact ? it.name : undefined}
                  onClick={() => onOpen(key)}
                  onPointerEnter={(e) => {
                    if (e.pointerType !== "mouse") return;
                    onHot(key);
                    hover.enter(key);
                  }}
                  onPointerLeave={(e) => {
                    if (e.pointerType !== "mouse") return;
                    onHot(null);
                    hover.leave();
                  }}
                  onFocus={(e) => {
                    onHot(key);
                    if (e.currentTarget.matches(":focus-visible")) hover.focus(key);
                  }}
                  onBlur={() => {
                    onHot(null);
                    hover.leave();
                  }}
                >
                  <span className="row-main">
                    <span className="row-name">{it.name}</span>
                    {(it.cuisine || area) && (
                      <span className="row-meta">
                        {it.cuisine && <span className="row-cuisine">{it.cuisine}</span>}
                        {area && <span className="row-area">{area}</span>}
                      </span>
                    )}
                  </span>
                  <span className="row-num">
                    <b>{it.people.toLocaleString()}</b>
                    <small>
                      {byMeaning && it.total_people != null
                        ? `of ${plural(it.total_people, "person", "people")}`
                        : it.people === 1 ? "person" : "people"}
                    </small>
                  </span>
                </button>
                {/* Keyed by the answer it belongs to: comments loaded for one
                    reading of the query are not shown under another. */}
                {!compact && (
                  <Evidence
                    key={`${city}|${query}|${data.mode}`} answer={`${city}|${query}|${data.mode}`}
                    item={it} matched={data.matched ?? null} dev={dev}
                  />
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

/**
 * The comments one result's count counts. The answer brings the first few;
 * the button reads the rest, a page at a time and in the answer's order,
 * until every comment behind the number is on screen. A count of the board's
 * own names no comments here: its row opens the place, which lists them all.
 *
 * What has been read is kept in lib/results (loaded), not only here: this is
 * taken down whenever the list is (a restaurant opened beside it, or over it
 * on a phone), and coming back must not ask for the same comments again.
 */
function Evidence({ answer, item, matched, dev }: { answer: string; item: SearchItem; matched: SearchMatched | null; dev: boolean }) {
  const id = resultId(item);
  const [read, setRead] = useState(() => loaded.get(answer, id));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => () => ctl.current?.abort(), []);
  // After the render, so the store is never written while React is drawing.
  useEffect(() => {
    if (read !== loaded.get(answer, id)) loaded.set(answer, id, read);
  }, [answer, id, read]);

  const shown = [...item.comments, ...read.extra];
  const next = nextRequest(item, read, matched !== null);
  const more = next && moreLabel(item, seenCount(item, read));
  const load = () => {
    if (!next || loading) return;
    const c = new AbortController();
    ctl.current = c;
    setLoading(true);
    setError(null);
    // The ids the answer named first; past them, a text match's comments
    // by their place in its order.
    const asked: Promise<(l: Loaded) => Loaded> = "ids" in next
      ? api.searchComments(next.ids, c.signal).then((rows) => (l) => afterIds(l, next.ids, rows))
      : api.searchMatched(item.entity_key, matched!, next.offset, next.limit, c.signal)
        .then((rows) => (l) => afterPage(item, l, next.limit, rows));
    asked.then(
      (apply) => {
        if (c.signal.aborted) return;
        setRead(apply);
        setLoading(false);
      },
      (e: unknown) => {
        if (c.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      },
    );
  };

  if (!shown.length && !more) return null;
  return (
    <>
      {shown.length > 0 && (
        <ol className="cmts sr-cmts">
          {shown.map((c) => <CommentCard key={c.mention_id} mention={c} dev={dev} />)}
        </ol>
      )}
      {more && (
        <p className="sr-more">
          <button type="button" className="textlink" disabled={loading} onClick={load}>
            {loading ? "Loading…" : more}
          </button>
          {error && <span role="alert"> These comments could not be loaded.</span>}
        </p>
      )}
    </>
  );
}
