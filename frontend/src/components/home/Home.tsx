import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import type { BoardResponse, City } from "../../api/types";
import { BRAND, TAGLINE } from "../../brand";
import type { FetchState } from "../../hooks/useFetch";
import { useWall } from "../../hooks/useWall";
import { countWord } from "../../lib/format";
import { stepIndex, wheelGestures } from "../../lib/gesture";
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
// How long after a wheel, touch, key or press a scroll still counts as the reader's.
const USER_SCROLL_MS = 1500;
// How far a finger has to travel to be a swipe rather than a tap.
const SWIPE_PX = 40;

/**
 * The landing page: the title and search over a wall of drifting cards,
 * then, one screen down, the cities over the map.
 *
 * Scrolling drives the hero's exit. `--p` runs from 0 to 1 as it leaves and
 * back again on the way up, and every layer's lift, fade and blur is
 * computed from it in CSS, so the exit reverses exactly. A small scroll
 * commits: once the reader has moved the page anywhere between the two
 * screens it is carried the rest of the way in the direction it was moving.
 *
 * On the cities the page holds still and a scroll steps the highlight
 * instead: one city per gesture, down the list and back up it, with the map
 * and the card following as they do on hover. Up from the first city leaves
 * for the title; down from the last does nothing.
 */
export function Home({ cities, citiesError, active, top, onActive, onOpen, onPlace, onTopic, hidden }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  const list = useRef<HTMLElement>(null);
  // Where the page was scrolled to, read before it is taken out of the flow.
  const lastY = useRef(0);
  const wasHidden = useRef(hidden);
  const pool = useWall(!hidden);

  // What the listeners below read: always the latest, without re-attaching them.
  const now = useRef({ cities, active, onActive, onOpen });
  now.current = { cities, active, onActive, onOpen };

  useEffect(() => {
    if (hidden) return;
    const el = root.current;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const wheel = wheelGestures();
    let raf = 0;
    let settle = 0;
    let auto = false;
    let lastQ: number | undefined;
    let heading: 1 | -1 = 1;
    // When the reader last did something that scrolls. The page also moves
    // on its own (a layout shift as fonts and the map arrive, the browser
    // restoring a position), and none of that may carry it anywhere.
    let userAt = -Infinity;
    let pressed = false;
    let touchY: number | null = null;
    const byUser = () => performance.now() - userAt < USER_SCROLL_MS;
    const touched = () => { userAt = performance.now(); };

    const between = (q: number) => q > 0.02 && q < 0.98;
    const progress = () => (hero.current ? Math.max(0, Math.min(1, window.scrollY / hero.current.offsetHeight)) : 0);
    // The carried scroll is over once scrolling has been quiet for a moment.
    // If it was cut short and the page rests between the two screens, it is
    // carried on; never while a scrollbar is held, and never before the
    // reader has scrolled at all.
    const rest = () => {
      auto = false;
      if (!calm && !pressed && userAt > -Infinity && between(progress())) carry(heading);
    };
    const carry = (to: 1 | -1) => {
      auto = true;
      // Armed here too: a carry to where the page already is scrolls nothing,
      // and would otherwise never be seen to end.
      window.clearTimeout(settle);
      settle = window.setTimeout(rest, 400);
      (to > 0 ? list.current : hero.current)?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
    };

    const update = () => {
      raf = 0;
      if (!el || !hero.current || !list.current) return;
      lastY.current = window.scrollY;
      if (calm) return;
      const q = progress();
      if (lastQ !== undefined && q !== lastQ) heading = q > lastQ ? 1 : -1;
      if (!auto && byUser() && lastQ !== undefined && q !== lastQ && between(q)) carry(heading);
      lastQ = q;
      el.style.setProperty("--p", Math.min(1, q / EXIT_AT).toFixed(4));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
      window.clearTimeout(settle);
      settle = window.setTimeout(rest, 160);
    };

    // ---- On the cities, a scroll steps through them instead of moving the page ----

    // Only while the whole screen of cities is in view. Where it is taller
    // than the window (a short one, or a phone with many cities stacked over
    // the card) the page has to scroll to be read, so it scrolls as usual.
    const stepping = () => {
      const h = hero.current;
      const c = list.current;
      return !!h && !!c && window.scrollY >= h.offsetHeight - 2 && c.offsetHeight <= window.innerHeight + 1;
    };
    const index = () => (now.current.cities ?? []).findIndex((c) => c.subreddit === now.current.active);
    const step = (dir: 1 | -1) => {
      const all = now.current.cities ?? [];
      const next = all[stepIndex(index(), dir, all.length)];
      if (next && next.subreddit !== now.current.active) now.current.onActive(next.subreddit);
    };
    // Up from the first city is the way back to the title.
    const stepOrLeave = (dir: 1 | -1) => (dir < 0 && index() <= 0 ? carry(-1) : step(dir));

    const onWheel = (e: WheelEvent) => {
      touched();
      if (e.ctrlKey) return;                 // a pinch-zoom, not a scroll
      const fresh = wheel.fresh(performance.now());
      if (auto) {
        // Coasting must neither cut a carry short nor step a city on arrival.
        e.preventDefault();
        wheel.spend();
        return;
      }
      if (!stepping()) {
        wheel.spend();
        return;
      }
      if (!fresh) {
        e.preventDefault();
        return;
      }
      const dir = e.deltaY > 0 ? 1 : e.deltaY < 0 ? -1 : 0;
      // Up from the first city is left to the page, which scrolls back to the hero.
      if (!dir || (dir < 0 && index() <= 0)) return;
      e.preventDefault();
      wheel.spend();
      step(dir);
    };

    const onKey = (e: KeyboardEvent) => {
      touched();
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      const target = e.target as HTMLElement;
      if (target.closest?.("input, textarea, select, [contenteditable]") || !stepping()) return;
      const dir = e.key === "ArrowDown" || e.key === "PageDown" ? 1 : e.key === "ArrowUp" || e.key === "PageUp" ? -1 : 0;
      if (dir) {
        e.preventDefault();
        const onName = !!target.closest?.(".city-name");
        stepOrLeave(dir);
        // Focus follows the highlight when it was on a name, so the two never part.
        if (onName) requestAnimationFrame(() => el?.querySelector<HTMLElement>('.city-name[aria-pressed="true"]')?.focus());
      } else if (e.key === "Enter" && !target.closest?.("button, a") && now.current.active) {
        e.preventDefault();
        now.current.onOpen(now.current.active);
      }
    };

    const onTouchStart = (e: TouchEvent) => {
      touched();
      touchY = stepping() && e.touches.length === 1 ? e.touches[0].clientY : null;
    };
    const onTouchMove = (e: TouchEvent) => {
      touched();
      if (touchY != null && e.cancelable) e.preventDefault();
    };
    const onTouchEnd = (e: TouchEvent) => {
      if (touchY == null) return;
      const dy = e.changedTouches[0].clientY - touchY;
      touchY = null;
      // A finger moving up is a scroll down. Less than this is a tap.
      if (Math.abs(dy) >= SWIPE_PX) stepOrLeave(dy < 0 ? 1 : -1);
    };
    const onDown = () => { pressed = true; touched(); };
    const onUp = () => { pressed = false; };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    window.addEventListener("pointerdown", onDown, { passive: true });
    window.addEventListener("pointerup", onUp, { passive: true });
    document.addEventListener("keydown", onKey);
    update();
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
      document.removeEventListener("keydown", onKey);
      if (raf) cancelAnimationFrame(raf);
      window.clearTimeout(settle);
    };
  }, [hidden]);

  // Opening a city takes this page out of the flow, which would snap it back
  // to its top mid-fade; pinning it where it was scrolled to lets it fade in
  // place. Coming back lands on the cities, where the reader left from. A
  // fresh load starts at the title, whatever position the browser remembers.
  const loaded = useRef(false);
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
        // With reduced motion nothing follows the scroll, so the hero is left as it is.
        if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) el.style.setProperty("--p", "1");
      } else if (!loaded.current) {
        window.history.scrollRestoration = "manual";
        window.scrollTo(0, 0);
      }
    }
    loaded.current = true;
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
              <p className="eyebrow">Highest rated right now</p>
              <p className="city-card-sub">
                r/{city.subreddit}
                {top.current && top.data ? `, ${top.data.total.toLocaleString()} places rated` : ""}
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
