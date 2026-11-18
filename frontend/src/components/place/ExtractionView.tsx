import { api } from "../../api/client";
import type { ExtractedMention } from "../../api/types";
import { useFetch } from "../../hooks/useFetch";
import { ago } from "../../lib/format";
import { currentCity } from "../../state/city";

const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0");

const LEVELS: [keyof ExtractedMention, string][] = [
  ["overall_level", "Overall"],
  ["taste_level", "Taste"],
  ["value_level", "Value"],
  ["service_level", "Service"],
  ["atmosphere_level", "Atmosphere"],
  ["wait_level", "Wait"],
];

function tone(n: number) {
  return n > 0 ? "ex-up" : n < 0 ? "ex-down" : "";
}

function Mention({ m }: { m: ExtractedMention }) {
  const levels = LEVELS.flatMap(([k, label]) => (typeof m[k] === "number" ? [[label, m[k] as number] as const] : []));
  const dishes = m.dish_opinions ?? [];
  const facts = [
    m.price_level != null && `Price ${signed(m.price_level)}`,
    m.timeframe,
    m.trend,
    m.status,
    m.avoid && "says avoid",
  ].filter(Boolean) as string[];
  const typed = m.resolved_name && m.resolved_name.toLowerCase() !== m.restaurant_raw.toLowerCase() ? m.restaurant_raw : null;

  return (
    <div className="ex-m">
      <b>{m.resolved_name ?? m.restaurant_raw}</b>
      {typed && <span className="ex-raw"> typed “{typed}”</span>}
      {levels.length > 0 && (
        <div className="ex-chips">
          {levels.map(([label, n]) => (
            <span key={label} className={`ex-chip ${tone(n)}`}>
              {label} {signed(n)}
            </span>
          ))}
        </div>
      )}
      {dishes.length > 0 && (
        <div className="ex-chips">
          {dishes.map((d, i) => (
            <span key={`${d.dish}${i}`} className={`ex-chip ${d.avoid ? "ex-down" : tone(d.level ?? 0)}`}>
              {d.dish}
              {d.level != null && ` ${signed(d.level)}`}
              {d.avoid && " (avoid)"}
            </span>
          ))}
        </div>
      )}
      {facts.length > 0 && <div className="ex-facts">{facts.join(" · ")}</div>}
    </div>
  );
}

/** What the extractor took from one comment or post, in place of its text.
 *  A debugging aid, only reachable with ?dev=1: it shows the rows of the
 *  city's v6 thread-mode prompt, and whether the item's latest read was
 *  that prompt's. */
export function ExtractionView({ itemId }: { itemId: string }) {
  const { data, current, error } = useFetch(`${currentCity()}|${itemId}`, () => api.extraction(itemId));
  if (error) return <p className="ex ex-note">{error}</p>;
  if (!current || !data) return <p className="ex ex-note">Loading…</p>;

  const s = data.state;
  return (
    <div className="ex">
      {data.groups.length === 0 && (
        <p className="ex-note">
          {!s
            ? "Not extracted yet"
            : !s.this_prompt
              ? "Not read with this prompt; its last read was with a different one"
              : s.pending
                ? "In a batch under this prompt; no result yet"
                : s.failed
                  ? "Extraction failed"
                  : s.extracted_at
                    ? `No mentions extracted (read ${ago(s.extracted_at)})`
                    : "Not extracted yet"}
        </p>
      )}
      {data.groups.map((g) => (
        <section key={g.prompt_hash}>
          <p className="ex-label">{g.label}</p>
          {g.mentions.map((m) => (
            <Mention key={m.mention_id} m={m} />
          ))}
        </section>
      ))}
      {data.groups.length > 0 && s && !s.this_prompt && (
        <p className="ex-note">Read again since with a different prompt.</p>
      )}
      {data.groups.length > 0 && s && s.this_prompt && s.pending && (
        <p className="ex-note">In a batch to be read again; these rows are from the read before.</p>
      )}
    </div>
  );
}
