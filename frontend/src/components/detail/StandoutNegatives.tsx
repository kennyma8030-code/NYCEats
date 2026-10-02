import { useFetch } from "../../hooks/useFetch";
import { api } from "../../api/client";
import type { LedgerItem } from "../../api/types";
import { ago, redditUrl } from "../../lib/format";

interface Props {
  item: LedgerItem;
}

/** Why a place is flagged under the new ranking: the harshest recent
 *  firsthand complaints, most upvoted first. Never a flag without these. */
export function StandoutNegatives({ item }: Props) {
  const { data } = useFetch(item.flagged ? item.entity_key : null, () =>
    api.standoutNegatives(item.entity_key),
  );
  if (!item.flagged) return null;
  const share = Math.round((item.strong_neg_share ?? 0) * 100);

  return (
    <div className="negs">
      <p className="lab">Standout complaints</p>
      <p className="negs-sum">
        {item.strong_neg_people} people had a bad time here in the last two years, {share}% of recent opinion.
      </p>
      <ul>
        {(data ?? []).slice(0, 3).map((m) => {
          const url = m.was_deleted_later ? null : redditUrl(m.permalink);
          const body = (m.body ?? "").length > 240 ? `${m.body!.slice(0, 240).trimEnd()}…` : m.body;
          return (
            <li key={m.mention_id}>
              <p>{body}</p>
              <span>
                {m.score ?? 0} points · {ago(m.created_utc)}
                {url && (
                  <>
                    {" · "}
                    <a href={url} target="_blank" rel="noreferrer">
                      Reddit
                    </a>
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
