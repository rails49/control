// @vitest-environment happy-dom

/**
 * An entry's row opened in the list under the roster: its time, its dwell,
 * its description and a Delete
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1358](https://github.com/rails49/control/issues/1358)).
 *
 * Four parts. What a typed field makes of an entry is `model/timetable.ts`'s.
 * Then `tc-entry`, the open row, which draws the fields and raises what a
 * person changed. Then `tc-requests`, which opens one row at a time. Then the
 * run view, which writes one `entry_wanted` for each change.
 */

import { describe, expect, it } from "vitest";

import { edited, same, type Entry } from "../src/model/timetable.js";

/** `goods` to `b.A` at 06:02, standing two minutes there. */
const GOODS: Entry = {
  at: "06:02",
  train: "goods",
  to: ["b.A"],
  dwell: 2,
  description: "meets the express",
};

/** An entry with no dwell and no description. */
const BARE: Entry = { at: "06:30", train: "local", to: ["c.B"] };

/** A turn-round. */
const TURN: Entry = { at: "06:10", train: "goods", turn: true };

describe("an entry with a field typed", () => {
  it("has a time typed as H:MM or HH:MM, said as HH:MM", () => {
    expect(edited(GOODS, "at", "6:10")).toEqual({ ...GOODS, at: "06:10" });
    expect(edited(GOODS, "at", " 23:59 ")).toEqual({ ...GOODS, at: "23:59" });
  });

  it.each(["", "soon", "0610", "24:00", "06:60"])("is not changed by %j, which is no time", (words) => {
    expect(edited(GOODS, "at", words)).toBeNull();
  });

  it("is not changed by the time it has", () => {
    expect(edited(GOODS, "at", "6:02")).toBeNull();
  });

  it("has a dwell typed as whole minutes", () => {
    expect(edited(GOODS, "dwell", "5")).toEqual({ ...GOODS, dwell: 5 });
    expect(edited(BARE, "dwell", " 3 ")).toEqual({ ...BARE, dwell: 3 });
  });

  /** A dwell of 0 is the key left out (BUS.md). */
  it.each(["0", ""])("has no dwell with %j typed", (words) => {
    expect(edited(GOODS, "dwell", words)).toEqual({
      at: "06:02",
      train: "goods",
      to: ["b.A"],
      description: "meets the express",
    });
  });

  it.each(["-1", "1.5", "two", "1e2"])("is not changed by a dwell of %j", (words) => {
    expect(edited(GOODS, "dwell", words)).toBeNull();
  });

  it("is not changed by the dwell it has, 0 where it has none", () => {
    expect(edited(GOODS, "dwell", "2")).toBeNull();
    expect(edited(BARE, "dwell", "0")).toBeNull();
    expect(edited({ ...BARE, dwell: 0 }, "dwell", "")).toBeNull();
  });

  /** A turn-round has no dwell, and the scheduler drops one that has. */
  it("is given no dwell where it is a turn-round", () => {
    expect(edited(TURN, "dwell", "2")).toBeNull();
  });

  it("has a description typed, the space round it dropped", () => {
    expect(edited(BARE, "description", " via the loop ")).toEqual({
      ...BARE,
      description: "via the loop",
    });
    expect(edited(TURN, "description", "runs round")).toEqual({
      ...TURN,
      description: "runs round",
    });
  });

  it("has no description once it is emptied", () => {
    expect(edited(GOODS, "description", " ")).toEqual({
      at: "06:02",
      train: "goods",
      to: ["b.A"],
      dwell: 2,
    });
  });

  it("is not changed by the description it has, or by none where it has none", () => {
    expect(edited(GOODS, "description", "meets the express")).toBeNull();
    expect(edited(BARE, "description", "")).toBeNull();
  });
});

describe("two entries", () => {
  it("are the same with every field of the document equal", () => {
    expect(same(GOODS, { ...GOODS, to: ["b.A"] })).toBe(true);
    expect(same(TURN, { ...TURN })).toBe(true);
  });

  it("are the same where one leaves out a dwell of 0 or an empty description", () => {
    expect(same(BARE, { ...BARE, dwell: 0, description: "" })).toBe(true);
  });

  it.each([
    ["time", { at: "06:03" }],
    ["train", { train: "local" }],
    ["arrival ends", { to: ["b.A", "c.B"] }],
    ["dwell", { dwell: 3 }],
    ["description", { description: "" }],
  ])("are not the same with another %s", (_, other) => {
    expect(same(GOODS, { ...GOODS, ...other })).toBe(false);
  });

  it("are not the same where one is a turn-round", () => {
    expect(same(TURN, { at: "06:10", train: "goods", to: ["b.A"] })).toBe(false);
  });
});
