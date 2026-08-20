/**
 * The recorded trace: JSONL from the bench tap, parsed and stepped one grant
 * boundary at a time. No DOM anywhere; a trace is text in and events out.
 */

import { describe, expect, it } from "vitest";

import { gesture, INBOUND, Live, parseTrace, Replay } from "../src/model/trace.js";

const SAMPLE = `
{"boundary":0,"event":"lock_granted","train":"t1","resources":["a"]}
{"boundary":0,"event":"boundary"}
{"boundary":1,"event":"boundary"}
{"boundary":1,"event":"block_occupied","block":"b"}
`;

describe("parseTrace", () => {
  it("reads one event per line and skips blank lines", () => {
    const events = parseTrace(SAMPLE);
    expect(events).toHaveLength(4);
    expect(events[0]).toMatchObject({
      boundary: 0,
      event: "lock_granted",
      train: "t1",
    });
  });

  it("refuses a line that is not an event", () => {
    expect(() => parseTrace('{"boundary":0,"event":"boundary"}\nnot json')).toThrow(
      /line 2/,
    );
    expect(() => parseTrace('{"no":"event field"}')).toThrow(/line 1/);
  });
});

describe("Replay", () => {
  it("steps one boundary stamp at a time", () => {
    const replay = new Replay(parseTrace(SAMPLE));
    expect(replay.done).toBe(false);
    expect(replay.boundary).toBe(null);
    const first = replay.step();
    expect(first.map((event) => event.event)).toEqual(["lock_granted", "boundary"]);
    expect(replay.boundary).toBe(0);
    const second = replay.step();
    expect(second.map((event) => event.event)).toEqual([
      "boundary",
      "block_occupied",
    ]);
    expect(replay.boundary).toBe(1);
    expect(replay.done).toBe(true);
    expect(replay.step()).toEqual([]);
  });

  it("restarts from the top", () => {
    const replay = new Replay(parseTrace(SAMPLE));
    replay.step();
    replay.step();
    replay.restart();
    expect(replay.done).toBe(false);
    expect(replay.boundary).toBe(null);
    expect(replay.step()).toHaveLength(2);
  });
});

describe("Live", () => {
  const frame = (topic: string, payload: Record<string, unknown> = {}) =>
    JSON.stringify({ topic, payload });

  it("reads a relayed frame as the event its topic leaf names", () => {
    const live = new Live();
    expect(live.read(frame("tc49/dispatch/lock_granted", { train: "t1" }))).toEqual({
      boundary: 0,
      event: "lock_granted",
      train: "t1",
    });
  });

  it("stamps every frame with the latest boundary, as the bench tap does", () => {
    const live = new Live();
    expect(live.boundary).toBeNull();
    live.read(frame("tc49/layout/boundary", { boundary: 7 }));
    expect(live.boundary).toBe(7);
    expect(live.read(frame("tc49/layout/block_occupied", { block: "b" }))).toEqual({
      boundary: 7,
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

describe("gesture", () => {
  it("wraps a drag in the one frame the relay accepts", () => {
    const wanted = { train: "t1", dest: ["b.A"] };
    expect(JSON.parse(gesture(wanted))).toEqual({
      topic: "tc49/ui/request_wanted",
      payload: wanted,
    });
    expect(INBOUND).toBe("tc49/ui/request_wanted");
  });

  it("carries no id and no departure end, those being the scheduler's", () => {
    const payload = JSON.parse(gesture({ train: "t1", dest: ["b.A"] })).payload;
    expect(Object.keys(payload).sort()).toEqual(["dest", "train"]);
  });
});
