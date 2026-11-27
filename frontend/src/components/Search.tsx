import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { SearchVocabulary } from "../api/types";
import { whereLine } from "../lib/format";
import { loadNames, search, suggest, type Entry, type NameHit } from "../lib/search";
import { matchTerms, termCount, type TermHit } from "../lib/terms";
import { Icon } from "./Icon";
import "./Search.css";

/** A city the box searches. */
export interface Scope {
  subreddit: string;
  name: string;
  short: string;
}

interface Props {
  /** The cities searched, in order: a bare Enter goes to the first. */
  scopes: Scope[];
  /** hero is the landing page's big bar; panel is the one in a city. */
  variant: "hero" | "panel";
  label: string;
  placeholder?: string;
  /** Example searches that take turns in an empty hero bar. */
  hints?: string[];
  onPlace: (subreddit: string, key: string) => void;
  onSearch: (subreddit: string, query: string) => void;
}

type Option =
  | { kind: "place"; scope: Scope; hit: NameHit }
  | { kind: "term"; scope: Scope; hit: TermHit }
  | { kind: "query"; scope: Scope };

const MAX_HITS = 6;
const MAX_TERMS = 3;

/**
 * One box for both kinds of search. Names are matched as you type, in the
 * browser (lib/search.ts), and listed under the box. Anything else is a
 * question for the city's comments: Enter on free text opens the city on
 * the places that answer it (/api/search). In a single city the box also
 * offers the cuisines, areas, dishes and descriptors the text could be the
 * start of (lib/terms.ts); picking one searches for it.
 *
 * Enter takes the highlighted row when the arrow keys have picked one, a
 * place when the text is exactly its name, and the search otherwise, so
 * "Katz's Delicatessen" opens Katz's and "date night" lists places for one.
 */
export function Search({ scopes, variant, label, placeholder, hints, onPlace, onSearch }: Props) {
  const id = useId();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [names, setNames] = useState<Record<string, Entry[]>>({});
  const [failed, setFailed] = useState(false);
  const [vocab, setVocab] = useState<Record<string, SearchVocabulary>>({});
  const input = useRef<HTMLInputElement>(null);
  const cities = scopes.map((s) => s.subreddit).join(",");

  // Names are fetched when the box is first used, not with the page: the
  // first city on focus, the rest once there is something to look up.
  const want = (subs: string[]) => {
    for (const sub of subs) {
      if (names[sub]) continue;
      loadNames(sub).then(
        (entries) => setNames((n) => (n[sub] ? n : { ...n, [sub]: entries })),
        () => setFailed(true),
      );
    }
    // The words of one city only: across several, a cuisine or an area would
    // need its city named beside it, and the box has the search rows for that.
    const only = scopes.length === 1 ? scopes[0].subreddit : null;
    if (only && !vocab[only]) {
      // Suggestions only: without them the box still searches.
      api.searchVocabulary(only).then((v) => setVocab((all) => (all[only] ? all : { ...all, [only]: v })), () => {});
    }
  };

  // Another set of cities is another search: nothing typed for the last one carries over.
  useEffect(() => {
    setQ("");
    setOpen(false);
    setActive(-1);
  }, [cities]);

  const text = q.trim();
  const { options, guessed } = useMemo(() => {
    if (!text) return { options: [] as Option[], guessed: false };
    const loaded = scopes.filter((s) => names[s.subreddit]);
    const found = loaded.flatMap((scope) =>
      search(names[scope.subreddit], text, MAX_HITS).map((hit) => ({ kind: "place" as const, scope, hit })));
    let places = found.sort((a, b) => b.hit.score - a.hit.score).slice(0, MAX_HITS);
    let guessed = false;
    // Nothing matched in any city: offer the nearest spellings instead.
    if (!places.length && loaded.length === scopes.length) {
      places = loaded.flatMap((scope) =>
        suggest(names[scope.subreddit], text, 3).map((hit) => ({ kind: "place" as const, scope, hit })))
        .sort((a, b) => b.hit.score - a.hit.score).slice(0, 3);
      guessed = places.length > 0;
    }
    const words = scopes.length === 1 ? vocab[scopes[0].subreddit] : undefined;
    const terms = words ? matchTerms(words, text, MAX_TERMS).map((hit) => ({ kind: "term" as const, scope: scopes[0], hit })) : [];
    const queries = scopes.map((scope) => ({ kind: "query" as const, scope }));
    return { options: [...places, ...terms, ...queries] as Option[], guessed };
  }, [text, names, vocab, scopes]);

  const places = options.filter((o): o is Extract<Option, { kind: "place" }> => o.kind === "place");
  const terms = options.filter((o): o is Extract<Option, { kind: "term" }> => o.kind === "term");
  const queries = options.filter((o): o is Extract<Option, { kind: "query" }> => o.kind === "query");
  const many = scopes.length > 1;

  const choose = (o: Option) => {
    setQ("");
    setOpen(false);
    setActive(-1);
    input.current?.blur();
    if (o.kind === "place") onPlace(o.scope.subreddit, o.hit.key);
    else onSearch(o.scope.subreddit, o.kind === "term" ? o.hit.label : text);
  };

  const submit = () => {
    if (!text) return;
    if (active >= 0 && options[active]) return choose(options[active]);
    const exact = guessed ? undefined : places.find((p) => p.hit.exact);
    choose(exact ?? { kind: "query", scope: scopes[0] });
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!options.length) return;
      e.preventDefault();
      setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      // -1 is the text itself, between the last row and the first.
      setActive((a) => ((a + 1 + step + options.length + 1) % (options.length + 1)) - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape" && (open || q)) {
      // Used here, so it does not also close the restaurant behind the box.
      e.preventDefault();
      if (open && text) setOpen(false);
      else setQ("");
      setActive(-1);
    }
  };

  const showList = open && text !== "";
  const optionId = (i: number) => `${id}-o${i}`;
  const sub = (o: Extract<Option, { kind: "place" }>) =>
    [whereLine(o.hit.cuisine, many ? o.scope.name : o.hit.borough), o.hit.closed ? "closed" : null].filter(Boolean).join(", ");

  return (
    <div
      className={`search in-${variant}`}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <label className="sr" htmlFor={id}>{label}</label>
      <Icon name="search" size={variant === "hero" ? 22 : 16} className="search-glass" />
      <input
        id={id} ref={input} type="search" autoComplete="off" spellCheck={false} enterKeyHint="search"
        role="combobox" aria-expanded={showList} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 ? optionId(active) : undefined}
        placeholder={hints ? undefined : placeholder}
        value={q}
        onFocus={() => {
          want([scopes[0].subreddit]);
          setOpen(true);
        }}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActive(-1);
          want(scopes.map((s) => s.subreddit));
        }}
        onKeyDown={onKey}
      />
      {hints && q === "" && (
        <div className="search-hints" aria-hidden="true">
          <div className="search-rot">
            {[...hints, hints[0]].map((h, i) => <div key={i}>{h}</div>)}
          </div>
        </div>
      )}
      {variant === "hero" && (
        <button type="button" className="search-go" aria-label="Search" onClick={submit}>
          <Icon name="arrow" size={20} stroke={2.4} />
        </button>
      )}

      {showList && (
        <div className="search-list pop" id={`${id}-list`} role="listbox" aria-label="Suggestions">
          {guessed && <p className="search-note">No exact match. Did you mean</p>}
          {places.map((o, i) => (
            <button
              key={`${o.scope.subreddit}|${o.hit.key}`} type="button" role="option" id={optionId(i)}
              aria-selected={i === active} className="search-opt" tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => choose(o)}
            >
              <span className="search-name">{o.hit.name}</span>
              <span className="search-sub">{sub(o)}</span>
              <span className="search-n">{o.hit.mentions.toLocaleString()} {o.hit.mentions === 1 ? "mention" : "mentions"}</span>
            </button>
          ))}
          {!places.length && !failed && Object.keys(names).length < scopes.length && <p className="search-note">Looking up names…</p>}
          {failed && <p className="search-note">Names could not be loaded.</p>}
          {many ? (
            <div className="search-topics">
              <p className="search-note">Places people bring up for “{text}” in</p>
              <div className="search-cities">
                {queries.map((o, j) => {
                  const i = places.length + terms.length + j;
                  return (
                    <button
                      key={o.scope.subreddit} type="button" role="option" id={optionId(i)} aria-selected={i === active}
                      className="search-city" tabIndex={-1}
                      onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => choose(o)}
                    >
                      {o.scope.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <>
            {terms.map((o, j) => {
              const i = places.length + j;
              return (
                <button
                  key={`${o.hit.kind}|${o.hit.label}`} type="button" role="option" id={optionId(i)} aria-selected={i === active}
                  className={j === 0 ? "search-opt term first" : "search-opt term"} tabIndex={-1}
                  onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => choose(o)}
                >
                  <span className="search-name">{o.hit.label}</span>
                  <span className="search-sub">{o.hit.kind}</span>
                  <span className="search-n">{termCount(o.hit)}</span>
                </button>
              );
            })}
            {queries.map((o, j) => {
              const i = places.length + terms.length + j;
              return (
                <button
                  key="query" type="button" role="option" id={optionId(i)} aria-selected={i === active}
                  className="search-opt topic" tabIndex={-1}
                  onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => choose(o)}
                >
                  <span className="search-name">Places people bring up for “{text}”</span>
                  <Icon name="arrow" size={16} className="search-n" />
                </button>
              );
            })}
            </>
          )}
        </div>
      )}
    </div>
  );
}
