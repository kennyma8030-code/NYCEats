import { api } from "../../api/client";
import type { SearchFilter, SearchResponse } from "../../api/types";
import { useFetch } from "../../hooks/useFetch";
import { plural } from "../../lib/format";
import { CommentCard } from "../place/Comments";
import "./SearchResults.css";

interface Props {
  query: string;
  /** The city searched. In the request's key so one city's answer never
   *  stands under another's name. */
  city: string;
  dev: boolean;
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
 * the fast one when it lands. If the full one fails, the fast one stays.
 */
export function SearchResults({ query, city, dev, onOpen, onClose }: Props) {
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
    <div className="sr">
      <div className="sr-head">
        <div className="sr-title">
          <h2>“{query}”</h2>
          <button type="button" className="textlink" onClick={onClose}>Clear search</button>
        </div>
        <p className="sr-sum">
          {fast.loading && !data
            ? "Searching…"
            : data
              ? `${plural(data.total, "place", "places")}, by how many people ` +
                (byMeaning ? "wrote a matching comment." : "brought them up.")
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
      </div>

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
        <ol className={reading ? "rows busy" : "rows"} aria-busy={fast.loading || reading}>
          {!data && Array.from({ length: 6 }, (_, i) => <li key={i} className="row-skel skel" aria-hidden="true" />)}
          {data?.items.map((it) => {
            const area = it.neighborhood ?? it.borough;
            return (
              <li key={it.entity_key} className="sr-item">
                <button type="button" className="row" data-key={it.entity_key} onClick={() => onOpen(it.entity_key)}>
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
                        ? `of ${it.total_people.toLocaleString()} people`
                        : it.people === 1 ? "person" : "people"}
                    </small>
                  </span>
                </button>
                {it.comments.length > 0 && (
                  <ol className="cmts sr-cmts">
                    {it.comments.map((c) => <CommentCard key={c.mention_id} mention={c} dev={dev} />)}
                  </ol>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
