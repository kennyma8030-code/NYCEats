import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { LedgerItem, WindowDays } from "../../api/types";
import { useFetch } from "../../hooks/useFetch";
import { useRestaurant } from "../../hooks/useRestaurant";
import { ago, plural, redditUrl, titleCase } from "../../lib/format";
import { BADGE_LABEL, CATEGORY_LABEL, complaintPhrase, isRankable, pct, people, rankableCategories } from "../../lib/rating";
import { sortOf } from "../../lib/sorts";
import { currentCity } from "../../state/city";
import { isLedgerSort, type SortId } from "../../state/route";
import { windowOf } from "../../state/filters";
import { Icon } from "../Icon";
import { CommentList, VoiceList, type VoiceView } from "./Comments";
import { Numbers } from "./Numbers";
import "./Place.css";

interface Props {
  entityKey: string;
  /** The place as a list row; null while it is still being fetched. */
  item: LedgerItem | null;
  error: string | null;
  /** Its number in the list it was opened from, when it is on it. */
  rank: number | null;
  sort: SortId;
  window: WindowDays;
  dev: boolean;
  onBack: () => void;
}

const n = (x: number) => x.toLocaleString();

// A complaint section is worth showing when complaints are a real share of
// opinion, not for the one bad night every busy place has.
const COMPLAINT_SHARE = 0.2;

/**
 * One restaurant, in the panel the list was in. Every number here is a
 * button that opens the comments it counts (VoiceList), and Escape or the
 * back button steps out one level: from those comments to the restaurant,
 * from the restaurant to the list.
 */
export function Place({ entityKey, item, error, rank, sort, window: win, dev, onBack }: Props) {
  const { data } = useRestaurant(entityKey);
  const [voices, setVoices] = useState<VoiceView | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const ready = item !== null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // A menu or the search box that used the key has already said so.
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (voices) setVoices(null);
      else onBack();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [voices, onBack]);

  // Move focus to the name once there is one, so a keyboard or a screen
  // reader starts at the restaurant rather than back at the list.
  useEffect(() => {
    if (ready) heading.current?.focus({ preventScroll: true });
  }, [ready, entityKey]);
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = 0;
  }, [voices]);

  const r = item?.rating ?? null;
  const worried = !!r && r.neg > 0 && (r.badge === "overhyped_mixed" || r.neg / Math.max(1, people(r)) >= COMPLAINT_SHARE);
  const negs = useFetch(worried ? `${currentCity()}|${entityKey}` : null, () => api.standoutNegatives(entityKey));

  if (!item) {
    return (
      <div className="place">
        <button type="button" className="back" onClick={onBack}>
          <Icon name="left" />
          Leaderboard
        </button>
        {error ? (
          <div className="board-msg" role="alert">
            <p>This restaurant could not be loaded.</p>
            <p className="board-msg-sub">{error}</p>
          </div>
        ) : (
          <div aria-busy="true" className="place-loading">
            <span className="skel" style={{ height: 14, width: "40%" }} />
            <span className="skel" style={{ height: 44, width: "80%" }} />
            <span className="skel" style={{ height: 120 }} />
          </div>
        )}
      </div>
    );
  }

  if (voices) {
    return (
      <div className="panel-scroll" ref={scroller}>
        <VoiceList
          key={`${entityKey}|${voices.voice}|${voices.category}`} entityKey={entityKey} placeName={item.name}
          view={voices} dev={dev} onBack={() => setVoices(null)}
        />
      </div>
    );
  }

  const ranked = isRankable(r);
  const complaints = r ? complaintPhrase(r) : null;
  const categories = r ? rankableCategories(r) : [];
  const kicker = [item.cuisine, item.neighborhood ?? item.borough].filter(Boolean).join(" · ");
  const where = data?.locations?.[0] ?? item.location ?? null;
  const count = data?.locations?.length ?? item.location_count ?? 0;
  const summary = data?.place_summary?.text ? data.place_summary : null;
  const dishes = data?.top_dishes.slice(0, 6) ?? [];
  const toComments = () => document.getElementById("place-comments")?.scrollIntoView({ behavior: "smooth", block: "start" });
  const ask = (view: VoiceView) => () => setVoices(view);
  const s = sortOf(sort);

  return (
    <div className="panel-scroll" ref={scroller}>
      <article className="place">
        <button type="button" className="back" onClick={onBack}>
          <Icon name="left" />
          Leaderboard
        </button>

        <header>
          {kicker && <p className="eyebrow">{kicker}</p>}
          <h2 className="place-name" tabIndex={-1} ref={heading}>{item.name}</h2>
          {where?.address && (
            <p className="place-where">
              {titleCase(where.address)}{where.borough ? `, ${where.borough}` : ""}
              {count > 1 ? ` · one of ${count} locations` : ""}
            </p>
          )}
        </header>

        <div className="place-rating">
          {ranked && r ? (
            <p className="place-rate">
              <button type="button" className="place-big" onClick={ask({ title: "Positive and negative", voice: "opinions", category: null })}
                aria-label={`${pct(r.pct_pos!)}% positive, ${plural(people(r), "person", "people")}. Show their comments`}>
                {pct(r.pct_pos!)}%
              </button>
              <span>
                <button type="button" className="textlink" onClick={ask({ title: "Positive and negative", voice: "opinions", category: null })}>
                  positive · {plural(people(r), "person", "people")}
                </button>
                {r.recommenders > 0 && (
                  <>
                    {" · "}
                    <button type="button" className="textlink" onClick={ask({ title: "Recommended by", voice: "recommenders", category: null })}>
                      recommended by {n(r.recommenders)}
                    </button>
                  </>
                )}
              </span>
            </p>
          ) : (
            <p className="place-rate small">
              <span>
                Not enough opinions yet to rate it.
                {r && r.recommenders > 0 && (
                  <>
                    {" "}
                    <button type="button" className="textlink" onClick={ask({ title: "Recommended by", voice: "recommenders", category: null })}>
                      Recommended by {n(r.recommenders)}
                    </button>
                  </>
                )}
                {r && people(r) > 0 && (
                  <>
                    {" · "}
                    <button type="button" className="textlink" onClick={ask({ title: "Stated opinions", voice: "opinions", category: null })}>
                      {people(r) === 1 ? "1 person has" : `${n(people(r))} people have`} given an opinion
                    </button>
                  </>
                )}
              </span>
            </p>
          )}
          <p className="place-notes">
            {ranked && r?.badge && <span className="badge">{BADGE_LABEL[r.badge]}</span>}
            {ranked && complaints && (
              <button type="button" className="textlink" onClick={ask({ title: "Complaints", voice: "neg", category: null })}>
                {complaints}
              </button>
            )}
            {ranked && r && r.superlative > 0 && (
              <button type="button" className="textlink" onClick={ask({ title: "Called it the best", voice: "superlative", category: null })}>
                {n(r.superlative)} called it the best
              </button>
            )}
          </p>
          {(rank != null || isLedgerSort(sort)) && (
            <p className="place-ctx">
              {rank != null && `No. ${rank} in ${s.label}`}
              {rank != null && isLedgerSort(sort) && " · "}
              {isLedgerSort(sort) && (
                <button type="button" className="textlink" onClick={toComments}>
                  {plural(item.current, "mention", "mentions")} in the last {windowOf(win).long}
                </button>
              )}
            </p>
          )}
        </div>

        {summary && (
          <section className="place-sec" aria-label="AI summary of the comments">
            <h3 className="eyebrow">What Reddit says</h3>
            <p className="place-summary">{summary.text}</p>
            <p className="place-quiet">
              AI summary
              {summary.comment_count ? (
                <>
                  {" of "}
                  <button type="button" className="textlink" onClick={toComments}>
                    {plural(summary.comment_count, "comment", "comments")}
                  </button>
                </>
              ) : ""}
              {summary.written_at
                ? ` · ${new Date(summary.written_at).toLocaleDateString("en-US", { month: "long", year: "numeric" })}`
                : ""}
            </p>
          </section>
        )}

        {dishes.length > 0 && (
          <section className="place-sec">
            <h3 className="eyebrow">People order</h3>
            <div className="tags">
              {dishes.map((d) => <span key={d.name} className="tag">{d.name}</span>)}
            </div>
          </section>
        )}

        {categories.length > 0 && (
          <section className="place-sec">
            <h3 className="eyebrow">Positive by aspect</h3>
            <ul className="bars">
              {categories.map((c) => (
                <li key={c.key}>
                  <button
                    type="button" className="bar"
                    aria-label={`${CATEGORY_LABEL[c.key]}: ${c.pct}% positive, ${plural(c.people, "person", "people")}. Show their comments`}
                    onClick={ask({ title: `${CATEGORY_LABEL[c.key]}: positive and negative`, voice: "opinions", category: c.key })}
                  >
                    <span className="bar-name">{CATEGORY_LABEL[c.key]}</span>
                    <span className="bar-track" aria-hidden="true"><i style={{ width: `${c.pct}%` }} /></span>
                    <span className="bar-num"><b>{c.pct}%</b> <small>{n(c.people)}</small></span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {worried && negs.current && negs.data && negs.data.length > 0 && r && (
          <section className="place-sec">
            <h3 className="eyebrow">Standout complaints</h3>
            <ul className="negs">
              {negs.data.slice(0, 2).map((m) => {
                const url = m.was_deleted_later ? null : redditUrl(m.permalink);
                const body = (m.body ?? "").trim();
                return (
                  <li key={m.mention_id}>
                    <p>{body.length > 260 ? `${body.slice(0, 260).trimEnd()}…` : body}</p>
                    <p className="cmt-meta">
                      {m.score != null && <span>{plural(m.score, "upvote", "upvotes")}</span>}
                      <span>{ago(m.created_utc)}</span>
                      {url ? <a href={url} target="_blank" rel="noopener noreferrer">Open on Reddit</a> : <span>Deleted from Reddit</span>}
                    </p>
                  </li>
                );
              })}
            </ul>
            <button type="button" className="textlink place-all" onClick={ask({ title: "Complaints", voice: "neg", category: null })}>
              All {plural(r.neg, "complaint", "complaints")}
            </button>
          </section>
        )}

        <CommentList key={entityKey} entityKey={entityKey} dev={dev} />

        <Numbers item={item} window={win} descriptors={data?.top_descriptors.slice(0, 8).map((d) => d.name) ?? []} />
      </article>
    </div>
  );
}
