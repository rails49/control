/**
 * The recorded trace: JSONL from the bench tap, parsed and stepped tick by
 * tick. No DOM anywhere; a trace is text in and events out.
 */

import { describe, expect, it } from "vitest";

import { INBOUND, Live, parseTrace, Replay, submission } from "../src/model/trace.js";

const SAMPLE = `
{"tick":0,"event":"lock_granted","train":"t1","resources":["a"]}
{"tick":0,"event":"tick"}
{"tick":1,"event":"tick"}
{"tick":1,"event":"block_occupied","block":"b"}
`;

describe("parseTrace", () => {
  it("reads one event per line and skips blank lines", () => {
    const events = parseTrace(SAMPLE);
    expect(events).toHaveLength(4);
    expect(events[0]).toMatchObject({
      tick: 0,
      event: "lock_granted",
      train: "t1",
    });
  });

  it("refuses a line that is not an event", () => {
    expect(() => parseTrace('{"tick":0,"event":"tick"}\nnot json')).toThrow(
      /line 2/,
    );
    expect(() => parseTrace('{"no":"event field"}')).toThrow(/line 1/);
  });
});

describe("Replay", () => {
  it("steps one tick stamp at a time", () => {
    const replay = new Replay(parseTrace(SAMPLE));
    expect(replay.done).toBe(false);
    expect(replay.tick).toBe(null);
    const first = replay.step();
    expect(first.map((event) => event.event)).toEqual(["lock_granted", "tick"]);
    expect(replay.tick).toBe(0);
    const second = replay.step();
    expect(second.map((event) => event.event)).toEqual([
      "tick",
      "block_occupied",
    ]);
    expect(replay.tick).toBe(1);
    expect(replay.done).toBe(true);
    expect(replay.step()).toEqual([]);
  });

  it("restarts from the top", () => {
    const replay = new Replay(parseTrace(SAMPLE));
    replay.step();
    replay.step();
    replay.restart();
    expect(replay.done).toBe(false);
    expect(replay.tick).toBe(null);
    expect(replay.step()).toHaveLength(2);
  });
});

describe("Live", () => {
  const frame = (topic: string, payload: Record<string, unknown> = {}) =>
    JSON.stringify({ topic, payload });

  it("reads a relayed frame as the event its topic leaf names", () => {
    const live = new Live();
    expect(live.read(frame("tc49/dispatch/lock_granted", { train: "t1" }))).toEqual({
      tick: 0,
      event: "lock_granted",
      train: "t1",
    });
  });

  it("stamps every frame with the latest tick, as the bench tap does", () => {
    const live = new Live();
    expect(live.tick).toBeNull();
    live.read(frame("tc49/layout/tick", { tick: 7 }));
    expect(live.tick).toBe(7);
    expect(live.read(frame("tc49/layout/block_occupied", { block: "b" }))).toEqual({
      tick: 7,
      event: "block_occupied",
      block: "b",
    });
  });

  it("ignores what is not a frame, an error one included", () => {
    const live = new Live();
    expect(live.read("not json")).toBeNull();
    expect(live.read(JSON.stringify({ error: "no" }))).toBeNull();
  });
});

describe("submission", () => {
  it("wraps a request in the one frame the relay accepts", () => {
    const request = { id: "t1-1", train: "t1", depart: "a.B", dest: ["b.A"] };
    expect(JSON.parse(submission(request))).toEqual({
      topic: INBOUND,
      payload: request,
    });
  });
});
