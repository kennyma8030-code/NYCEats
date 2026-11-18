import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import type { BoardResponse, City } from "../../api/types";
import { BRAND, TAGLINE } from "../../brand";
import type { FetchState } from "../../hooks/useFetch";
import { useWall } from "../../hooks/useWall";
import { countWord } from "../../lib/format";
import { isRankable, pct } from "../../lib/rating";
import { Icon } from "../Icon";
import { MapCredit } from "../MapCredit";
import { Search, type Scope } from "../Search";
import { Wall } from "./Wall";
import "./Home.css";

interface Props {
  cities: City[] | null;
  citiesError: string | null;
  /** The city highlighted in the list, which the map behind is showing. */
  active: string;
  /** That city's best-liked few, which are also the pins on the map behind. */
  top: FetchState<BoardResponse>;
  onActive: (subreddit: string) => void;
  onOpen: (subreddit: string) => void;
  onPlace: (subreddit: string, key: string) => void;
  onTopic: (subreddit: string, topic: string) => void;
  /** True while a city is open: the page fades out and stops taking part. */
  hidden: boolean;
}

// Real searches of both kinds: a topic lists the places people bring up
// under it, a name opens that restaurant.
const HINTS = ["omakase", "Katz's Delicatessen", "date night", "birria tacos", "tasting menu"];

// How much of the hero has to scroll away for its exit to be complete. The
// title is gone well before the next screen has fully arrived.
const EXIT_AT = 0.55;

/**
 * The landing page: the title and search over a wall of drifting cards,
 * then, one screen down, the cities over the map.
 *
 * Scrolling drives the hero's exit. `--p` runs from 0 to 1 as it leaves and
 * back again on the way up, and every layer's lift, fade and blur is
 * computed from it in CSS, so the exit reverses exactly. A small scroll
 * commits: once the page rests anywhere between the two screens it is
 * carried the rest of the way in the direction it was moving.
 */
export function Home({ cities, citiesError, active, top, onActive, onOpen, onPlace, onTopic, hidden }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  const list = useRef<HTMLElement>(null);
  // Where the page was scrolled to, read before it is taken out of the flow.
  const lastY = useRef(0);
  const wasHidden = useRef(hidden);
  const pool = useWall(!hidden);

  useEffect(() => {
    if (hidden) return;
    const el = root.current;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let settle = 0;
    let auto = false;
    let lastQ: number | undefined;

    const update = () => {
      raf = 0;
      const h = hero.current;
      const c = list.current;
      if (!el || !h || !c) return;
      lastY.current = window.scrollY;
      if (calm) return;
      const q = Math.max(0, Math.min(1, window.scrollY / h.offsetHeight));
      if (!auto && lastQ !== undefined && q !== lastQ && q > 0.02 && q < 0.98) {
        auto = true;
        (q > lastQ ? c : h).scrollIntoView({ behavior: "smooth", block: "start" });
      }
      lastQ = q;
      el.style.setProperty("--p", Math.min(1, q / EXIT_AT).toFixed(4));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
      // The carried scroll is over once scrolling has been quiet for a moment.
      window.clearTimeout(settle);
      settle = window.setTimeout(() => { auto = false; }, 160);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    update();
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
      window.clearTimeout(settle);
    };
  }, [hidden]);

  // Opening a city takes this page out of the flow, which would snap it back
  // to its top mid-fade; pinning it where it was scrolled to lets it fade in
  // place. Coming back lands on the cities, where the reader left from.
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    if (hidden) {
      el.style.top = `${-lastY.current}px`;
      el.setAttribute("inert", "");
    } else {
      el.style.top = "";
      el.removeAttribute("inert");
      if (wasHidden.current && hero.current) {
        window.scrollTo(0, hero.current.offsetHeight);
        el.style.setProperty("--p", "1");
      }
    }
    wasHidden.current = hidden;
  }, [hidden]);

  const scopes: Scope[] = useMemo(
    () => (cities ?? []).map((c) => ({ subreddit: c.subreddit, name: c.name, short: c.short })),
    [cities],
  );
  const city = cities?.find((c) => c.subreddit === active) ?? null;
  const three = top.current && top.data ? top.data.items.filter((i) => isRankable(i.rating)) : null;

  return (
    <div className={hidden ? "home gone" : "home"} ref={root} aria-hidden={hidden}>
      <section className="hero" ref={hero}>
        <Wall pool={pool} />
        <div className="hero-front">
          <h1 className="hero-title">
            {BRAND.first} <span>{BRAND.second}</span>
          </h1>
          <p className="hero-tag">{TAGLINE}</p>
          <div className="hero-search">
            {scopes.length > 0 && (
              <Search
                scopes={scopes} variant="hero" label="Search a restaurant, dish or neighborhood" hints={HINTS}
                onPlace={onPlace} onTopic={onTopic}
              />
            )}
          </div>
        </div>
        <button
          type="button" className="hero-cue"
          onClick={() => list.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
        >
          Pick a city
          <Icon name="down" size={28} className="bob" />
        </button>
      </section>

      <section className="cities" ref={list} aria-label="Cities">
        <div className="cities-wash" aria-hidden="true" />
        <div className="cities-list">
          <p className="cities-kicker">
            {cities ? `${countWord(cities.length)} ${cities.length === 1 ? "city" : "cities"}` : "Cities"}
          </p>
          {cities?.map((c) => {
            const on = c.subreddit === active;
            return (
              <button
                key={c.subreddit} type="button" className="city-name" aria-pressed={on}
                onMouseEnter={() => onActive(c.subreddit)} onFocus={() => onActive(c.subreddit)}
                onClick={() => onOpen(c.subreddit)}
              >
                {c.name}
                {on && <Icon name="arrow" size={36} stroke={2.6} />}
              </button>
            );
          })}
          {!cities && !citiesError && [0, 1, 2].map((i) => <span key={i} className="city-name skel" aria-hidden="true">&nbsp;</span>)}
          {citiesError && (
            <p className="cities-err" role="alert">
              The cities could not be loaded: {citiesError}{" "}
              <button type="button" className="textlink" onClick={() => window.location.reload()}>Try again</button>
            </p>
          )}
        </div>

        {city && (
          <div className="city-card pop" key={city.subreddit}>
            <div>
              <p className="eyebrow">Most loved right now</p>
              <p className="city-card-sub">
                r/{city.subreddit}
                {top.current && top.data ? ` · ${top.data.total.toLocaleString()} places ranked` : ""}
              </p>
            </div>
            {three && three.length > 0 && (
              <ol className="city-top">
                {three.map((item, i) => (
                  <li key={item.entity_key}>
                    <span className="city-top-n">{i + 1}</span>
                    <button type="button" className="city-top-name" onClick={() => onPlace(city.subreddit, item.entity_key)}>
                      {item.name}
                    </button>
                    <span className="city-top-pct">{pct(item.rating!.pct_pos!)}%</span>
                  </li>
                ))}
              </ol>
            )}
            {!three && !top.error && (
              <div className="city-top" aria-hidden="true">
                {[0, 1, 2].map((i) => <span key={i} className="skel city-top-skel" />)}
              </div>
            )}
            {three && three.length === 0 && <p className="city-card-sub">Not enough opinions yet to rank anywhere.</p>}
            {top.error && <p className="city-card-sub">The ranking could not be loaded. The city still opens.</p>}
            <button type="button" className="pill solid city-open" onClick={() => onOpen(city.subreddit)}>
              Open {city.name}
              <Icon name="arrow" size={18} stroke={2.4} />
            </button>
          </div>
        )}
        <MapCredit />
      </section>
    </div>
  );
}
