/**
 * The bus's payloads: what the broker delivers on a topic read as events, and
 * the frames the browser publishes back. No DOM anywhere; a topic and its text
 * in, an event out.
 */

import { describe, expect, it } from "vitest";

import {
  CANCEL_WANTED,
  cancellation,
  DRIVING_WANTED,
  drivingWanted,
  FUNCTION_WANTED,
  functionWanted,
  gesture,
  Live,
  Ordering,
  POINT_WANTED,
  pointWanted,
  POWER_WANTED,
  powerWanted,
  REORDER_WANTED,
  reorderWanted,
  REQUEST_WANTED,
  reversal,
  REVERSAL_WANTED,
  STATE_NAMES,
  TAKE_WANTED,
  takeWanted,
  THROTTLE_ALIVE,
  throttleAlive,
  THROTTLE_WANTED,
  throttleWanted,
  trackLive,
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

/** The throttle being turned (#207): the sixth. One number for the train,
 *  signed for the way the train points — which locomotive it reaches, and
 *  which way round that one stands, is `layout`'s (GLOSSARY.md,
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

  it("names the throttle turning the lever where it is given one", () => {
    expect(throttleWanted("t1", 0.4, "k3x9").payload).toEqual({
      train: "t1",
      speed: 0.4,
      throttle: "k3x9",
    });
    expect(throttleWanted("t1", 0.4).payload).not.toHaveProperty("throttle");
  });
});

/** One throttle holds a train (ADR-0079): a take names the throttle by the
 *  id its page minted, and `null` releases the train whoever holds it. */
describe("takeWanted", () => {
  it("names the train and the throttle that is to hold it", () => {
    expect(takeWanted("t1", "k3x9")).toEqual({
      topic: "tc49/layout/take_wanted",
      payload: { train: "t1", throttle: "k3x9" },
    });
    expect(TAKE_WANTED).toBe("tc49/layout/take_wanted");
  });

  it("releases on an explicit null", () => {
    expect(takeWanted("t1", null).payload).toEqual({ train: "t1", throttle: null });
  });
});

/** A throttle switches one of its train's functions by the name the
 *  catalogue gives it (#849). */
describe("functionWanted", () => {
  it("names the train, the throttle holding it, the function and the bit", () => {
    expect(functionWanted("t1", "k3x9", "headlights", true)).toEqual({
      topic: "tc49/layout/function_wanted",
      payload: {
        train: "t1",
        throttle: "k3x9",
        function: "headlights",
        on: true,
      },
    });
    expect(FUNCTION_WANTED).toBe("tc49/layout/function_wanted");
  });
});

describe("throttleAlive", () => {
  it("names the throttle and nothing else", () => {
    expect(throttleAlive("k3x9")).toEqual({
      topic: "tc49/layout/throttle_alive",
      payload: { throttle: "k3x9" },
    });
    expect(THROTTLE_ALIVE).toBe("tc49/layout/throttle_alive");
  });
});

describe("drivingWanted", () => {
  it("names the railroad's driving mode and nothing else", () => {
    expect(drivingWanted("automatic")).toEqual({
      topic: "tc49/layout/driving_wanted",
      payload: { driving: "automatic" },
    });
    expect(drivingWanted("manual").payload).toEqual({ driving: "manual" });
    expect(DRIVING_WANTED).toBe("tc49/layout/driving_wanted");
  });
});

/** Commanding track power (ADR-0051, ADR-0078): the same three values the
 *  layout reports, in the command direction. */
describe("powerWanted", () => {
  it("names where the supply should stand and nothing else", () => {
    expect(powerWanted("draining")).toEqual({
      topic: "tc49/layout/power_wanted",
      payload: { power: "draining" },
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

/** The one reading of "the track has power": on, or draining, which keeps
 *  the supply on until nothing is moving (ADR-0078). */
describe("trackLive", () => {
  it.each([
    ["on", true],
    ["draining", true],
    ["off", false],
    [null, false],
  ] as const)("reads %s as live: %s", (power, live) => {
    expect(trackLive(power)).toBe(live);
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
    expect(ordering.accepts(power(1, "draining"))).toBe(true);
  });

  it("reads no stamp off anything but a number", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(20, "on"))).toBe(true);
    // `true` is not a number here; in Python it is an `int`, which is why
    // that reader refuses a boolean in a line of its own.
    expect(ordering.accepts({ event: "power", at: true, power: "off" })).toBe(true);
    expect(ordering.accepts({ event: "power", at: "20", power: "off" })).toBe(true);
    expect(ordering.accepts(power(1, "draining"))).toBe(true);
  });

  it("holds a stamp per state topic and not one for the page", () => {
    const ordering = new Ordering();
    expect(ordering.accepts(power(20, "off"))).toBe(true);
    expect(ordering.accepts({ event: "moving", at: 1, moving: false })).toBe(true);
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
   *  device rows a view reads are among them under the name `Live` gives
   *  each: a state row like the rest, so a pair delivered backwards must not
   *  leave a trip on the band after the hardware has stopped saying so
   *  (#602), nor a detector's older reading at its block end (#898). */
  it("names every state topic a view is shown", () => {
    expect([...STATE_NAMES].sort()).toEqual([
      "allocation",
      "aspects",
      "clock",
      "device/sensor",
      "device/track",
      "disputed",
      "driving",
      "exhausted",
      "facing",
      "functions",
      "moving",
      "power",
      "railroad",
      "taken",
      "unfit",
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

  /** A device row addressed under its name is one topic per address, so a
   *  reading at one block end is ordered against that end's alone (#898). */
  it("orders a detector's readings by the end it watches", () => {
    const ordering = new Ordering();
    const sensor = (at: number, addr: string) => ({
      event: "device/sensor",
      at,
      addr,
      occupancy: "clear",
    });
    expect(ordering.accepts(sensor(20, "a.A"))).toBe(true);
    expect(ordering.accepts(sensor(10, "b.B"))).toBe(true);
    expect(ordering.accepts(sensor(10, "a.A"))).toBe(false);
  });
});

/** The waiting requests are a list a person orders (ADR-0080): a cancel
 *  names one request by id, and a reorder moves one in front of another or,
 *  with `null`, to the end. */
describe("cancellation", () => {
  it("names the request and nothing else", () => {
    expect(cancellation("r1")).toEqual({
      topic: "tc49/dispatch/cancel_wanted",
      payload: { id: "r1" },
    });
    expect(CANCEL_WANTED).toBe("tc49/dispatch/cancel_wanted");
  });
});

describe("reorderWanted", () => {
  it("names the request and the one it goes in front of", () => {
    expect(reorderWanted("r2", "r1")).toEqual({
      topic: "tc49/dispatch/reorder_wanted",
      payload: { id: "r2", before: "r1" },
    });
    expect(REORDER_WANTED).toBe("tc49/dispatch/reorder_wanted");
  });

  it("writes an explicit null for the end of the list", () => {
    expect(reorderWanted("r1", null).payload).toEqual({ id: "r1", before: null });
  });
});
