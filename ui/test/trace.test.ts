/**
 * The live feed's payloads: the frames the bridge relays read as events, and
 * the frames the browser writes back. No DOM anywhere; a frame is text in and
 * an event out.
 */

import { describe, expect, it } from "vitest";

import {
  gesture,
  Live,
  REQUEST_WANTED,
  reversal,
  REVERSAL_WANTED,
  RUN_WANTED,
  runWanted,
} from "../src/model/trace.js";

describe("Live", () => {
  const frame = (topic: string, payload: Record<string, unknown> = {}) =>
    JSON.stringify({ topic, payload });

  it("reads a relayed frame as the event its topic leaf names", () => {
    const live = new Live();
    expect(live.read(frame("tc49/dispatch/lock_granted", { train: "t1" }))).toEqual({
      event: { event: "lock_granted", train: "t1" },
    });
  });

  /** No payload carries a timestamp and the tap's `time` is the harness's
   *  own (ADR-0047), so a frame is the payload and its leaf, whole. */
  it("adds nothing of its own to a frame", () => {
    const live = new Live();
    const heard = live.read(frame("tc49/layout/block_occupied", { block: "b" }));
    expect(heard).toEqual({ event: { event: "block_occupied", block: "b" } });
  });

  /** The relay's `{error}` is the whole of what a session says about itself
   *  going wrong — a refused frame, or a path naming no scenario (#148) — and
   *  the panel shows it as trouble. Dropping it left a refusal invisible. */
  it("hands back the relay's refusal rather than dropping it", () => {
    const live = new Live();
    expect(live.read(JSON.stringify({ error: "no scenario 'gotthard/nope'" }))).toEqual(
      { error: "no scenario 'gotthard/nope'" },
    );
  });

  it("ignores what is not a frame at all", () => {
    const live = new Live();
    expect(live.read("not json")).toBeNull();
    expect(live.read(JSON.stringify({ topic: 7, payload: {} }))).toBeNull();
    expect(live.read(JSON.stringify({ error: 7 }))).toBeNull();
  });
});

describe("gesture", () => {
  it("wraps a drag in the one frame the relay accepts", () => {
    const wanted = { train: "t1", dest: ["b.A"] };
    expect(JSON.parse(gesture(wanted))).toEqual({
      topic: "tc49/schedule/request_wanted",
      payload: wanted,
    });
    expect(REQUEST_WANTED).toBe("tc49/schedule/request_wanted");
  });

  it("carries no id and no departure end, those being the scheduler's", () => {
    const payload = JSON.parse(gesture({ train: "t1", dest: ["b.A"] })).payload;
    expect(Object.keys(payload).sort()).toEqual(["dest", "train"]);
  });
});

/** Turning a train around at rest (#124): the second thing the page may
 *  write, and the train is the whole of it — no destination, because nothing
 *  moves, and no id, because a gesture carries none. */
describe("reversal", () => {
  it("names the train and nothing else", () => {
    expect(JSON.parse(reversal("t1"))).toEqual({
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
    expect(JSON.parse(runWanted("held"))).toEqual({
      topic: "tc49/dispatch/run_wanted",
      payload: { run: "held" },
    });
    expect(JSON.parse(runWanted("running")).payload).toEqual({ run: "running" });
    expect(RUN_WANTED).toBe("tc49/dispatch/run_wanted");
  });
});
