// Telling one scroll gesture from the stream of wheel events it arrives as.
// Pure, so it can be tested without a browser (frontend/tests).

/** Wheel events closer together than this are one gesture: a trackpad flick
 *  keeps sending them for a second or more as it coasts, and a spun wheel
 *  sends one per notch. */
export const WHEEL_GAP_MS = 200;

/**
 * One flick or one spin of the wheel is many events, and a step taken on
 * each would run through a whole list. This marks where a gesture begins (the
 * first event after a quiet gap) and lets it be spent once; every later
 * event of the same gesture, its coasting included, reports as used.
 */
export function wheelGestures(gap: number = WHEEL_GAP_MS) {
  let last = -Infinity;
  let spent = false;
  return {
    /** Feed every wheel event its time. True while this gesture is still unspent. */
    fresh(now: number): boolean {
      if (now - last > gap) spent = false;
      last = now;
      return !spent;
    },
    /** The gesture has done its one thing, or began somewhere it must not act. */
    spend(): void {
      spent = true;
    },
  };
}

/** The index one step from `index` in a list of `count`, held at both ends.
 *  Nothing highlighted yet (-1) steps onto the first. */
export function stepIndex(index: number, dir: 1 | -1, count: number): number {
  if (count <= 0) return -1;
  if (index < 0) return 0;
  return Math.max(0, Math.min(count - 1, index + dir));
}
