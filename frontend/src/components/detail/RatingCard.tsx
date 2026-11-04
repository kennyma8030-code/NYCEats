import type { Rating } from "../../api/types";
import {
  BADGE_LABEL, CATEGORY_LABEL, complaintPhrase, isRankable, pct, people, rankableCategories,
} from "../../lib/rating";
import type { VoiceView } from "./VoiceList";

interface Props {
  rating: Rating | null | undefined;
  onVoices: (view: VoiceView) => void;
}

const n = (x: number) => x.toLocaleString();

/** How much the sub likes a place, apart from how many bring it up. Every
 *  number opens the comments behind it. */
export function RatingCard({ rating: r, onVoices }: Props) {
  if (!r) {
    return (
      <section className="rt" aria-label="Rating">
        <p className="lab">Rating</p>
        <p className="rt-quiet">Not enough people yet.</p>
      </section>
    );
  }

  const posNeg = (title: string, category: VoiceView["category"], pos: number, neg: number, start: "pos" | "neg" = "pos"): VoiceView => ({
    title,
    category,
    start,
    tabs: [
      { voice: "pos", label: "Positive", count: pos },
      { voice: "neg", label: "Negative", count: neg },
    ],
  });
  const single = (title: string, voice: "recommenders" | "neg" | "superlative", label: string, count: number): VoiceView => ({
    title, category: null, start: voice, tabs: [{ voice, label, count }],
  });

  // Too few people to say: the counts that exist, a quiet line, no badge.
  if (!isRankable(r)) {
    return (
      <section className="rt" aria-label="Rating">
        <p className="lab">Rating</p>
        <p className="rt-quiet">Not enough people yet.</p>
        <p className="rt-counts">
          {r.recommenders > 0 && (
            <button type="button" className="rt-link" onClick={() => onVoices(single("Recommended by", "recommenders", "Recommended", r.recommenders))}>
              Recommended by {n(r.recommenders)}
            </button>
          )}
          {people(r) > 0 && (
            <button type="button" className="rt-link" onClick={() => onVoices(posNeg("Stated opinions", null, r.pos, r.neg))}>
              {n(people(r))} {people(r) === 1 ? "person has" : "people have"} given an opinion
            </button>
          )}
        </p>
      </section>
    );
  }

  const complaints = complaintPhrase(r.neg_share);
  const cats = rankableCategories(r);

  return (
    <section className="rt" aria-label="Rating">
      <p className="lab">Rating</p>
      <p className="rt-head">
        <button type="button" className="rt-link" onClick={() => onVoices(posNeg("Positive and negative", null, r.pos, r.neg))}>
          <b>{pct(r.pct_pos!)}% positive</b> · {n(people(r))} {people(r) === 1 ? "person" : "people"}
        </button>
        <span aria-hidden="true"> · </span>
        <button type="button" className="rt-link" onClick={() => onVoices(single("Recommended by", "recommenders", "Recommended", r.recommenders))}>
          recommended by {n(r.recommenders)}
        </button>
      </p>
      <p className="rt-notes">
        {r.badge && <span className={`rt-badge ${r.badge}`}>{BADGE_LABEL[r.badge]}</span>}
        {complaints && r.neg > 0 && (
          <button type="button" className="rt-link" onClick={() => onVoices(single("Complaints", "neg", "Negative", r.neg))}>
            {complaints}
          </button>
        )}
        {r.superlative > 0 && (
          <button type="button" className="rt-link" onClick={() => onVoices(single("Called it the best", "superlative", "Called it the best", r.superlative))}>
            {n(r.superlative)} called it the best
          </button>
        )}
      </p>
      {cats.length > 0 && (
        <ul className="rt-cats">
          {cats.map((c) => (
            <li key={c.key}>
              <button
                type="button"
                className="rt-cat"
                aria-label={`${CATEGORY_LABEL[c.key]}: ${c.pct}% positive, ${n(c.people)} people. Show comments`}
                onClick={() => onVoices(posNeg(`${CATEGORY_LABEL[c.key]}: positive and negative`, c.key, c.pos, c.neg))}
              >
                <span className="rt-name">{CATEGORY_LABEL[c.key]}</span>
                <span className="rt-bar" aria-hidden="true">
                  <i style={{ width: `${c.pct}%` }} />
                </span>
                <span className="rt-num">
                  <b>{c.pct}%</b> <small>{n(c.people)}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
