/**
 * The bus's payloads: what the broker delivers on a topic read as events, and
 * the frames the browser publishes back. No DOM anywhere; a topic and its text
 * in, an event out.
 */

import { describe, expect, it } from "vitest";

import {
  DRAINING,
  gesture,
  Live,
  MODE_WANTED,
  modeWanted,
  Ordering,
  POWER_WANTED,
  powerWanted,
  REQUEST_WANTED,
  reversal,
  REVERSAL_WANTED,
  RUN_WANTED,
  runWanted,
  STATE_LEAVES,
  THROTTLE_WANTED,
  throttleWanted,
} from "../src/model/trace.js";

describe("Live", () => {
  it("reads a message as the event its topic leaf names", () => {
    const live = new Live();
    expect(
      live.read("tc49/dispatch/lock_granted", JSON.stringify({ train: "t1" })),
    ).toEqual({ event: "lock_granted", train: "t1" });
  });

  /** No payload carries a timestamp and the tap's `time` is the harness's
   *  own (ADR-0047), so an event is the payload and its leaf, whole. */
  it("adds nothing of its own to a message", () => {
    const live = new Live();
    const heard = live.read("tc49/layout/block_occupied", JSON.stringify({ block: "b" }));
    expect(heard).toEqual({ event: "block_occupied", block: "b" });
  });

  /** A retained row is cleared by publishing an empty payload on it, which is
   *  a message like any other as far as this is concerned: nothing to apply,
   *  and nothing to fall over. */
  it("ignores what is not a JSON object", () => {
    const live = new Live();
    expect(live.read("tc49/dispatch/state/run", "")).toBeNull();
    expect(live.read("tc49/dispatch/state/run", "not json")).toBeNull();
    expect(live.read("tc49/dispatch/state/run", "7")).toBeNull();
    expect(live.read("tc49/dispatch/state/run", "[1]")).toBeNull();
    expect(live.read("tc49/dispatch/state/run", "null")).toBeNull();
  });
});

describe("gesture", () => {
  it("names the topic a drag is published on and what goes on it", () => {
    const wanted = { train: "t1", dest: ["b.A"] };
    expect(gesture(wanted)).toEqual({
      topic: "tc49/schedule/request_wanted",
      payload: wanted,
    });
    expect(REQUEST_WANTED).toBe("tc49/schedule/request_wanted");
  });

  it("carries no id and no departure end, those being the scheduler's", () => {
    const { payload } = gesture({ train: "t1", dest: ["b.A"] });
    expect(Object.keys(payload).sort()).toEqual(["dest", "train"]);
  });
});

/** Turning a train around at rest (#124): the second thing the page may
 *  write, and the train is the whole of it — no destination, because nothing
 *  moves, and no id, because a gesture carries none. */
describe("reversal", () => {
  it("names the train and nothing else", () => {
    expect(reversal("t1")).toEqual({
      topic: "tc49/schedule/reversal_wanted",
      payload: { train: "t1" },
    });
    expect(REVERSAL_WANTED).toBe("tc49/schedule/reversal_wanted");
  });
});

/** Holding the run and releasing it (ADR-0037): the third thing the page may
 *  write. It says where the run should stand rather than asking for a change,
 *  so two presses of the same value are not a race. */
describe("runWanted", () => {
  it("names where the run should stand and nothing else", () => {
    expect(runWanted("held")).toEqual({
      topic: "tc49/dispatch/run_wanted",
      payload: { run: "held" },
    });
    expect(runWanted("running").payload).toEqual({ run: "running" });
    expect(RUN_WANTED).toBe("tc49/dispatch/run_wanted");
  });

  /** The drain is a third value of the same word rather than a state of its
   *  own (#123, #294), and it is what the band's OFF asks for first
   *  (ADR-0051). `state/run` reads it back like any other value of the run,
   *  and what the OFF sequence waits for is the `held` the dispatcher writes
   *  itself when the drain completes. */
  it("carries the drain on the same word", () => {
    expect(runWanted(DRAINING).payload).toEqual({ run: "draining" });
  });
});

/** Taking a train in a throttle and giving it back (#207): the fifth thing
 *  the page may write. It names where the mode should stand rather than
 *  asking for a change, as the run's and the supply's gestures do, and who is
 *  driving is read back off `state/mode` rather than assumed from the press. */
describe("modeWanted", () => {
  it("names the train and where its mode should stand", () => {
    expect(modeWanted("t1", "manual")).toEqual({
      topic: "tc49/layout/mode_wanted",
      payload: { train: "t1", mode: "manual" },
    });
    expect(modeWanted("t1", "automatic").payload).toEqual({
      train: "t1",
      mode: "automatic",
    });
    expect(MODE_WANTED).toBe("tc49/layout/mode_wanted");
  });
});

/** The throttle being turned (#207): the sixth. One number for the train,
 *  signed for the way the train points — which locomotive it reaches, and
 *  which way round that one stands, is `layout`'s (CONTEXT.md,
 *  **Throttle**). */
describe("throttleWanted", () => {
  it("names the train and one speed", () => {
    expect(throttleWanted("t1", -0.5)).toEqual({
      topic: "tc49/layout/throttle_wanted",
      payload: { train: "t1", speed: -0.5 },
    });
    expect(THROTTLE_WANTED).toBe("tc49/layout/throttle_wanted");
  });

  it("carries a stop as the number zero", () => {
    expect(throttleWanted("t1", 0).payload).toEqual({
      train: "t1",
      speed: 0,
    });
  });
});

/** Commanding track power (ADR-0051): the same three values the layout
 *  reports, in the command direction. One topic and one axis, so no consumer
 *  has to decide what powered-off-and-emergency-stopped means. */
describe("powerWanted", () => {
  it("names where the supply should stand and nothing else", () => {
    expect(powerWanted("stopped")).toEqual({
      topic: "tc49/layout/power_wanted",
      payload: { power: "stopped" },
    });
    expect(powerWanted("on").payload).toEqual({ power: "on" });
    expect(powerWanted("off").payload).toEqual({ power: "off" });
    expect(POWER_WANTED).toBe("tc49/layout/power_wanted");
  });

  /** It is `layout`'s because `layout` answers it, and `layout` answers by
   *  writing the desired power of the device vocabulary — a page never
   *  reaches the hardware itself (ADR-0043, ADR-0051). */
  it("is the layout's topic and not a translator's", () => {
    expect(POWER_WANTED.startsWith("tc49/layout/")).toBe(true);
    expect(STATE_LEAVES.has("power_wanted")).toBe(false);
  });
});


/** The stamp a state payload carries, and the order two values of one topic
 *  are kept in (#240). The browser's half of the rule `tc49.lib.payload`
 *  keeps in Python: MQTT promises order from one publisher on one topic, and
 *  a pair delivered backwards would leave a page showing the older value. */
describe("Ordering", () => {
  const power = (at: number | undefined, value: string) =>
    at === undefined
      ? { event: "power", power: value }
      : { event: "power", at, power: value };

  it("keeps the later of two values and ignores the earlier", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(20, "on"))).toBe(true);
    expect(ordering.accepts(power(10, "off"))).toBe(false);
  });

  it("lets an equal stamp replace", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(10, "on"))).toBe(true);
    expect(ordering.accepts(power(10, "off"))).toBe(true);
  });

  it("takes an unstamped value and clears the held stamp", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(20, "on"))).toBe(true);
    expect(ordering.accepts(power(undefined, "off"))).toBe(true);
    expect(ordering.accepts(power(1, "stopped"))).toBe(true);
  });

  it("reads no stamp off anything but a number", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(20, "on"))).toBe(true);
    // `true` is not a number here; in Python it is an `int`, which is why
    // that reader refuses a boolean in a line of its own.
    expect(ordering.accepts({ event: "power", at: true, power: "off" })).toBe(true);
    expect(ordering.accepts({ event: "power", at: "20", power: "off" })).toBe(true);
    expect(ordering.accepts(power(1, "stopped"))).toBe(true);
  });

  it("holds a stamp per state topic and not one for the page", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(20, "off"))).toBe(true);
    expect(ordering.accepts({ event: "run", at: 1, run: "held" })).toBe(true);
  });

  it("orders no event topic at all", () => {
    const ordering = new Ordering();
    expect(ordering.accepts({ event: "block_occupied", at: 20, block: "a" })).toBe(
      true,
    );
    expect(ordering.accepts({ event: "block_vacated", at: 1, block: "a" })).toBe(true);
  });

  it("forgets its stamps when a page starts over", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(20, "off"))).toBe(true);
    ordering.reset();
    expect(ordering.accepts(power(1, "on"))).toBe(true);
  });

  /** The leaves are the state rows of `tc49.lib.inventory`, and a Python
   *  test reads this list out of the file to keep the two from drifting. */
  it("names every state leaf a view is shown", () => {
    expect([...STATE_LEAVES].sort()).toEqual([
      "allocation",
      "aspects",
      "disputed",
      "exhausted",
      "facing",
      "mode",
      "power",
      "railroad",
      "run",
    ]);
  });
});
