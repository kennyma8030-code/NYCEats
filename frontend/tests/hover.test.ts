// When a row's preview opens, changes and closes, on a clock the test
// winds by hand. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { hoverIntent, type HoverTimings, type Scheduler } from "../src/lib/hover.ts";

const T: HoverTimings = { open: 150, swap: 60, close: 240 };

function setup() {
  let now = 0;
  let timers: { at: number; fn: () => void }[] = [];
  const clock: Scheduler = {
    set: (fn, ms) => {
      const timer = { at: now + ms, fn };
      timers.push(timer);
      return timer;
    },
    clear: (handle) => {
      timers = timers.filter((x) => x !== handle);
    },
  };
  const shown: (string | null)[] = [];
  const intent = hoverIntent((key) => shown.push(key), T, clock);
  const wait = (ms: number) => {
    now += ms;
    const due = timers.filter((x) => x.at <= now);
    timers = timers.filter((x) => x.at > now);
    due.forEach((x) => x.fn());
  };
  return { intent, shown, wait };
}

test("a pointer sweeping down the list opens nothing", () => {
  const { intent, shown, wait } = setup();
  for (const key of ["a", "b", "c", "d"]) {
    intent.enter(key);
    wait(40);
    intent.leave();
  }
  wait(1000);
  assert.deepEqual(shown, []);
});

test("resting on a row opens its preview after the delay, and not before", () => {
  const { intent, shown, wait } = setup();
  intent.enter("a");
  wait(149);
  assert.deepEqual(shown, []);
  wait(1);
  assert.deepEqual(shown, ["a"]);
});

test("once open, another row replaces it promptly and without closing first", () => {
  const { intent, shown, wait } = setup();
  intent.enter("a");
  wait(150);
  intent.leave();
  intent.enter("b");
  wait(60);
  assert.deepEqual(shown, ["a", "b"]);
});

test("it stays up while the pointer crosses from the row to the preview", () => {
  const { intent, shown, wait } = setup();
  intent.enter("a");
  wait(150);
  intent.leave();
  wait(200);
  intent.hold();
  wait(5000);
  assert.deepEqual(shown, ["a"]);
});

test("it closes shortly after the pointer leaves the row and the preview both", () => {
  const { intent, shown, wait } = setup();
  intent.enter("a");
  wait(150);
  intent.leave();
  intent.hold();
  intent.leave();
  wait(239);
  assert.deepEqual(shown, ["a"]);
  wait(1);
  assert.deepEqual(shown, ["a", null]);
});

test("a row brushed on the way to the preview does not replace it", () => {
  const { intent, shown, wait } = setup();
  intent.enter("a");
  wait(150);
  intent.leave();
  intent.enter("b");
  wait(30);
  intent.leave();
  intent.hold();
  wait(1000);
  assert.deepEqual(shown, ["a"]);
});

test("coming back to the open row cancels the close", () => {
  const { intent, shown, wait } = setup();
  intent.enter("a");
  wait(150);
  intent.leave();
  wait(100);
  intent.enter("a");
  wait(1000);
  assert.deepEqual(shown, ["a"]);
});

test("keyboard focus shows at once, and cancel takes it down at once", () => {
  const { intent, shown, wait } = setup();
  intent.now("a");
  assert.deepEqual(shown, ["a"]);
  intent.now("b");
  intent.cancel();
  assert.deepEqual(shown, ["a", "b", null]);
  // Nothing was left waiting to reopen it.
  wait(1000);
  assert.deepEqual(shown, ["a", "b", null]);
});

test("cancel before the delay is up means it never opens", () => {
  const { intent, shown, wait } = setup();
  intent.enter("a");
  wait(100);
  intent.cancel();
  wait(1000);
  assert.deepEqual(shown, []);
});
