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

const RECOMMENDERS: VoiceView = { title: "Recommended by", voice: "recommenders", category: null };

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

  const ranked = isRankable(r);
  const complaints = complaintPhrase(r);
  const cats = rankableCategories(r);

  return (
    <section className="rt" aria-label="Rating">
      <p className="lab">Rating</p>
      {ranked ? (
        <>
          <p className="rt-head">
            <button
              type="button"
              className="rt-link"
              onClick={() => onVoices({ title: "Positive and negative", voice: "opinions", category: null })}
            >
              <b>{pct(r.pct_pos!)}% positive</b> · {n(people(r))} {people(r) === 1 ? "person" : "people"}
            </button>
            <span aria-hidden="true"> · </span>
            <button type="button" className="rt-link" onClick={() => onVoices(RECOMMENDERS)}>
              recommended by {n(r.recommenders)}
            </button>
          </p>
          <p className="rt-notes">
            {r.badge && <span className={`rt-badge ${r.badge}`}>{BADGE_LABEL[r.badge]}</span>}
            {complaints && (
              <button type="button" className="rt-link" onClick={() => onVoices({ title: "Complaints", voice: "neg", category: null })}>
                {complaints}
              </button>
            )}
            {r.superlative > 0 && (
              <button
                type="button"
                className="rt-link"
                onClick={() => onVoices({ title: "Called it the best", voice: "superlative", category: null })}
              >
                {n(r.superlative)} called it the best
              </button>
            )}
          </p>
        </>
      ) : (
        <>
          <p className="rt-quiet">Not enough people yet.</p>
          <p className="rt-counts">
            {r.recommenders > 0 && (
              <button type="button" className="rt-link" onClick={() => onVoices(RECOMMENDERS)}>
                Recommended by {n(r.recommenders)}
              </button>
            )}
            {people(r) > 0 && (
              <button
                type="button"
                className="rt-link"
                onClick={() => onVoices({ title: "Stated opinions", voice: "opinions", category: null })}
              >
                {n(people(r))} {people(r) === 1 ? "person has" : "people have"} given an opinion
              </button>
            )}
          </p>
        </>
      )}
      {cats.length > 0 && (
        <ul className="rt-cats">
          {cats.map((c) => (
            <li key={c.key}>
              <button
                type="button"
                className="rt-cat"
                aria-label={`${CATEGORY_LABEL[c.key]}: ${c.pct}% positive, ${n(c.people)} people. Show comments`}
                onClick={() => onVoices({ title: `${CATEGORY_LABEL[c.key]}: positive and negative`, voice: "opinions", category: c.key })}
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
