/**
 * The recorded trace: JSONL from the bench tap, parsed and stepped tick by
 * tick. No DOM anywhere; a trace is text in and events out.
 */

import { describe, expect, it } from "vitest";

import { parseTrace, Replay } from "../src/model/trace.js";

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
