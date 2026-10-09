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
  POINT_WANTED,
  pointWanted,
  POWER_WANTED,
  powerWanted,
  REQUEST_WANTED,
  reversal,
  REVERSAL_WANTED,
  RUN_WANTED,
  runWanted,
  STATE_NAMES,
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

  /** A device row is named by two levels where every other row is named by
   *  one, exactly as `tc49.lib.trace` names one (ADR-0043): the address is
   *  trailing levels a railroad's wiring decides, and `track` alone would not
   *  say which half of the vocabulary a frame is from. */
  it("names a device row the way the inventory does", () => {
    const live = new Live();
    expect(
      live.read(
        "tc49/layout/state/device/track",
        JSON.stringify({ power: "on", reason: "district B tripped" }),
      ),
    ).toEqual({ event: "device/track", power: "on", reason: "district B tripped" });
  });

  /** What `layout` asked the hardware for and what the hardware answered are
   *  two rows under one leaf, and a page is handed both: the desired half
   *  carries no reason, so a page that read them as one name would clear a
   *  trip on the next power press. */
  it("tells the desired supply from the observed one", () => {
    const live = new Live();
    expect(live.read("tc49/layout/state/wanted/track", JSON.stringify({ power: "off" })))
      .toEqual({ event: "wanted/track", power: "off" });
  });

  /** The address says nothing, so the name stops where the row does. */
  it("names an addressed device row without its address", () => {
    const live = new Live();
    expect(
      live.read(
        "tc49/layout/state/device/sensor/b.A",
        JSON.stringify({ addr: "b.A", occupancy: "occupied" }),
      )!.event,
    ).toBe("device/sensor");
  });

  /** Only the device vocabulary is named that way. Everything else under the
   *  layout interface is one level and reads as its leaf. */
  it("reads the layout's own state rows as leaves", () => {
    const live = new Live();
    expect(live.read("tc49/layout/state/power", JSON.stringify({ power: "on" }))).toEqual(
      { event: "power", power: "on" },
    );
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

/** Throwing a point by hand (ADR-0068, #666): a click on a point asks the
 *  dispatcher for a position, and it is the one that judges it. */
describe("pointWanted", () => {
  it("names the address and the position and nothing else", () => {
    expect(pointWanted({ addr: "7", position: "thrown" })).toEqual({
      topic: "tc49/dispatch/point_wanted",
      payload: { addr: "7", position: "thrown" },
    });
    expect(POINT_WANTED).toBe("tc49/dispatch/point_wanted");
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
    expect(STATE_NAMES.has("power_wanted")).toBe(false);
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

  /** The names are the state rows of `tc49.lib.inventory`, and a Python
   *  test reads this list out of the file to keep the two from drifting. The
   *  one device row a view reads is among them under the name `Live` gives
   *  it: it is a state row like the rest, so a pair delivered backwards must
   *  not leave a trip on the band after the hardware has stopped saying so
   *  (#602). */
  it("names every state topic a view is shown", () => {
    expect([...STATE_NAMES].sort()).toEqual([
      "allocation",
      "aspects",
      "device/track",
      "disputed",
      "exhausted",
      "facing",
      "mode",
      "power",
      "railroad",
      "run",
    ]);
  });

  /** The device row is ordered like every other state row, the stamp being
   *  what tells two values of one topic apart (#240). */
  it("orders the device row it is shown", () => {
    const ordering = new Ordering();
    const track = (at: number, reason?: string) => ({
      event: "device/track",
      at,
      power: "on",
      ...(reason === undefined ? {} : { reason }),
    });
    expect(ordering.accepts(track(20))).toBe(true);
    expect(ordering.accepts(track(10, "district B tripped"))).toBe(false);
  });
});
