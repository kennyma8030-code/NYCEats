// When a hovered row's preview opens, changes and closes. Pure, with the
// timer handed in, so the timing can be tested without a browser
// (frontend/tests).

export interface HoverTimings {
  /** Resting on a row this long opens its preview: a pointer sweeping down
   *  the list passes each row faster than that and opens nothing. */
  open: number;
  /** Once a preview is open, another row replaces it this soon. */
  swap: number;
  /** How long the preview outlives the pointer leaving the row and the
   *  preview both: long enough to cross the gap between them. */
  close: number;
}

export const HOVER: HoverTimings = { open: 150, swap: 60, close: 240 };

export interface Scheduler {
  set(fn: () => void, ms: number): unknown;
  clear(handle: unknown): void;
}

const TIMEOUTS: Scheduler = {
  set: (fn, ms) => setTimeout(fn, ms),
  clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/**
 * `show` is called with the key whose preview should be up, and with null
 * when none should. It is only called when that changes.
 */
export function hoverIntent(show: (key: string | null) => void, t: HoverTimings = HOVER, clock: Scheduler = TIMEOUTS) {
  let shown: string | null = null;
  let pending: unknown = null;
  let closing: unknown = null;

  const stop = () => {
    if (pending !== null) clock.clear(pending);
    if (closing !== null) clock.clear(closing);
    pending = closing = null;
  };
  const put = (key: string | null) => {
    if (key === shown) return;
    shown = key;
    show(key);
  };

  return {
    /** The pointer came onto a row. */
    enter(key: string): void {
      stop();
      if (key === shown) return;
      pending = clock.set(() => {
        pending = null;
        put(key);
      }, shown === null ? t.open : t.swap);
    },
    /** The pointer left a row, or the preview itself. */
    leave(): void {
      stop();
      if (shown === null) return;
      closing = clock.set(() => {
        closing = null;
        put(null);
      }, t.close);
    },
    /** The pointer is on the preview: it stays as it is. */
    hold(): void {
      stop();
    },
    /** Show a row's preview at once: keyboard focus has no sweep to wait out. */
    now(key: string): void {
      stop();
      put(key);
    },
    /** Take the preview down at once. */
    cancel(): void {
      stop();
      put(null);
    },
  };
}

export type HoverIntent = ReturnType<typeof hoverIntent>;
