import { describe, expect, it } from "vitest";

import type { Drawing, SymbolSpec, Wire } from "../src/model/drawing.js";
import type { Point } from "../src/model/geometry.js";
import { wiring, type Stroke, type Worn } from "../src/render/wires.js";

function drawing(symbols: Record<string, SymbolSpec>, wires: Wire[]): Drawing {
  return { drawing: "test", symbols, wires };
}

/** A bend with its pin at a face centre: `(c, r + 0.5)`. */
function bend(c: number, r: number): SymbolSpec {
  return { kind: "pin", at: [c, r] };
}

const UNLIT = new Map<string, Worn>();

function near(got: Point | undefined, x: number, y: number): void {
  expect(got?.x).toBeCloseTo(x);
  expect(got?.y).toBeCloseTo(y);
}

/** The straight strokes and the corners, apart. */
function parts(strokes: readonly Stroke[]): { lines: Stroke[]; corners: Stroke[] } {
  return {
    lines: strokes.filter((stroke) => stroke.round === undefined),
    corners: strokes.filter((stroke) => stroke.round !== undefined),
  };
}

/**
 * What is drawn for a drawing's wires (#1297): each wire's straight part, and
 * a curve wherever a run changes direction.
 */
describe("a run that keeps its direction", () => {
  const level = drawing(
    {
      west: { kind: "block", at: [0, 0] },
      p1: bend(8, 0),
      east: { kind: "block", at: [10, 0] },
    },
    [
      ["west.B", "p1.P"],
      ["p1.P", "east.A"],
    ],
  );

  it("is one straight stroke for each wire, pin to pin", () => {
    const { strokes } = wiring(level, UNLIT);
    expect(strokes).toEqual([
      { from: { x: 6, y: 0.5 }, to: { x: 8, y: 0.5 } },
      { from: { x: 8, y: 0.5 }, to: { x: 10, y: 0.5 } },
    ]);
  });

  it("cuts no symbol's track short", () => {
    expect(wiring(level, UNLIT).cuts.size).toBe(0);
  });
});

describe("a bend whose two wires are not in line", () => {
  const D = Math.SQRT1_2;

  /** Level from a block to a bend at (8, 0.5), down at 45 degrees to a bend
   *  at (10, 2.5), and level again. */
  const dogleg = drawing(
    {
      west: { kind: "block", at: [0, 0] },
      p1: bend(8, 0),
      p2: bend(10, 2),
      east: { kind: "block", at: [12, 2] },
    },
    [
      ["west.B", "p1.P"],
      ["p1.P", "p2.P"],
      ["p2.P", "east.A"],
    ],
  );

  it("joins them with one curve round the pin, begun the turnout's curve short of it", () => {
    const { corners } = parts(wiring(dogleg, UNLIT).strokes);
    expect(corners).toHaveLength(2);
    near(corners[0]!.from, 8 - D, 0.5);
    near(corners[0]!.round, 8, 0.5);
    near(corners[0]!.to, 8.5, 1);
    near(corners[1]!.from, 9.5, 2);
    near(corners[1]!.round, 10, 2.5);
    near(corners[1]!.to, 10 + D, 2.5);
  });

  it("stops each wire where its curve begins", () => {
    const { lines } = parts(wiring(dogleg, UNLIT).strokes);
    near(lines[0]!.from, 6, 0.5);
    near(lines[0]!.to, 8 - D, 0.5);
    near(lines[1]!.from, 8.5, 1);
    near(lines[1]!.to, 9.5, 2);
    near(lines[2]!.from, 10 + D, 2.5);
    near(lines[2]!.to, 12, 2.5);
  });

  it("turns a right angle the same way", () => {
    const square = drawing(
      {
        west: { kind: "block", at: [0, 0] },
        p1: bend(8, 0),
        p2: bend(8, 3),
      },
      [
        ["west.B", "p1.P"],
        ["p1.P", "p2.P"],
      ],
    );
    const { corners } = parts(wiring(square, UNLIT).strokes);
    expect(corners).toHaveLength(1);
    near(corners[0]!.from, 8 - D, 0.5);
    near(corners[0]!.round, 8, 0.5);
    near(corners[0]!.to, 8, 0.5 + D);
  });

  it("gives each corner half of a wire too short for two", () => {
    // p1 at (8, 0.5) and p2 at (8.5, 1) are 0.71 apart.
    const tight = drawing(
      {
        west: { kind: "block", at: [0, 0] },
        p1: bend(8, 0),
        p2: { kind: "pin", at: [8, 1], rot: 90 },
        p3: { kind: "pin", at: [10, 1], rot: 90 },
      },
      [
        ["west.B", "p1.P"],
        ["p1.P", "p2.P"],
        ["p2.P", "p3.P"],
      ],
    );
    const { corners } = parts(wiring(tight, UNLIT).strokes);
    expect(corners).toHaveLength(2);
    near(corners[0]!.to, 8.25, 0.75);
    near(corners[1]!.from, 8.25, 0.75);
    near(corners[1]!.to, 8.5 + D, 1);
  });

  it("draws no curve at a bend with one wire, or two that double back", () => {
    const back = drawing(
      { p1: bend(8, 0), p2: bend(10, 0), p3: bend(12, 0) },
      [
        ["p1.P", "p3.P"],
        ["p3.P", "p2.P"],
      ],
    );
    expect(parts(wiring(back, UNLIT).strokes).corners).toEqual([]);
  });

  it("lights a corner as the more strongly claimed of its two wires", () => {
    const corner = (worn: Record<string, Worn>) =>
      parts(wiring(dogleg, new Map(Object.entries(worn))).strokes).corners[0]!;
    expect(corner({}).worn).toBeUndefined();
    expect(corner({ "p1.P west.B": { classes: "lit" } }).worn).toEqual({ classes: "lit" });
    expect(corner({ "p1.P p2.P": { classes: "lit offending" } }).worn).toEqual({
      classes: "lit offending",
    });
    expect(
      corner({
        "p1.P west.B": { classes: "lit committed", colour: "var(--train-teal)" },
        "p1.P p2.P": { classes: "lit locked", colour: "var(--train-gold)" },
      }).worn,
    ).toEqual({ classes: "lit locked", colour: "var(--train-gold)" });
    expect(
      corner({
        "p1.P west.B": { classes: "lit occupied" },
        "p1.P p2.P": { classes: "lit locked" },
      }).worn,
    ).toEqual({ classes: "lit occupied" });
  });

  it("tells the canvas the bend's own dot is off the track", () => {
    expect(wiring(dogleg, UNLIT).cuts.get("p1")?.has("P")).toBe(true);
    expect(wiring(dogleg, UNLIT).cuts.has("west")).toBe(false);
  });
});

/**
 * A symbol's track runs to its pin, so a curve there has to begin on that
 * track. The curve is drawn in two halves: the symbol draws its own, from
 * where its track stops to the middle of the curve, so that half is lit,
 * faint or selected as the symbol is; the wire's half is a stroke here.
 */
describe("a wire leaving a symbol's pin out of line with its track", () => {
  const D = Math.SQRT1_2;
  const STRAIGHT = 1 - D; // a diverging road's straight start, from the toe

  /** The strokes and the cuts of a drawing with one wire. */
  function turning(symbols: Record<string, SymbolSpec>, wire: Wire) {
    const { strokes, cuts } = wiring(drawing(symbols, [wire]), UNLIT);
    return { ...parts(strokes), cuts };
  }

  it("stops the block's stub short, and hands the block its half of the curve", () => {
    // west.B at (6, 0.5), its stub level; the wire leaves down at 45 degrees,
    // so the curve runs from (5.29, 0.5) round the pin to (6.5, 1).
    const { cuts } = turning(
      { west: { kind: "block", at: [0, 0] }, p1: bend(8, 2) },
      ["west.B", "p1.P"],
    );
    const taken = cuts.get("west")?.get("B");
    expect(taken?.by).toBeCloseTo(D);
    near(taken?.mid, 5.948, 0.625);
    expect(cuts.get("west")?.has("A")).toBe(false);
  });

  it("draws the wire's half from the middle of the curve", () => {
    const { corners, lines } = turning(
      { west: { kind: "block", at: [0, 0] }, p1: bend(8, 2) },
      ["west.B", "p1.P"],
    );
    expect(corners).toHaveLength(1);
    near(corners[0]!.from, 5.948, 0.625);
    near(corners[0]!.round, 6.25, 0.75);
    near(corners[0]!.to, 6.5, 1);
    near(lines[0]!.from, 6.5, 1);
    near(lines[0]!.to, 8, 2.5);
  });

  it("gives a turned or flipped symbol the middle in its own coordinates", () => {
    // Flipped, the block's A is at (6, 0.5): the same curve on the sheet,
    // which the block sees mirrored.
    const flipped = turning(
      { west: { kind: "block", at: [0, 0], flip: true }, p1: bend(8, 2) },
      ["west.A", "p1.P"],
    );
    near(flipped.cuts.get("west")?.get("A")?.mid, 6 - 5.948, 0.625);
    near(flipped.corners[0]!.to, 6.5, 1);
    // On end, the block's B is at (0.5, 6) and its stub runs down to it.
    const upright = turning(
      {
        up: { kind: "block", at: [0, 0], rot: 90 },
        p1: { kind: "pin", at: [2, 8], rot: 90 },
      },
      ["up.B", "p1.P"],
    );
    near(upright.cuts.get("up")?.get("B")?.mid, 5.948, 0.375);
  });

  it("cuts an unturned turnout's toe only as far as both its roads are straight", () => {
    // toe at (10, 0.5), level; the wire is 0.71 long, to (9.5, 1).
    const { corners, cuts } = turning(
      {
        sw: { kind: "turnout", at: [10, 0] },
        p1: { kind: "pin", at: [9, 1], rot: 90 },
      },
      ["sw.toe", "p1.P"],
    );
    expect(cuts.get("sw")?.get("toe")?.by).toBeCloseTo(STRAIGHT);
    near(cuts.get("sw")?.get("toe")?.mid, 0.011, 0.5625);
    near(corners[0]!.from, 10.011, 0.5625);
    near(corners[0]!.to, 9.75, 0.75);
  });

  it("leaves an unturned turnout's diverging pin alone, its track being a curve to the pin", () => {
    // diverging at (11.5, 0), leaving up and right; the wire goes straight up.
    const { corners, lines, cuts } = turning(
      {
        sw: { kind: "turnout", at: [10, 0] },
        p1: { kind: "pin", at: [11, -2], rot: 90 },
      },
      ["sw.diverging", "p1.P"],
    );
    expect(corners).toEqual([]);
    expect(cuts.size).toBe(0);
    near(lines[0]!.from, 11.5, 0);
    near(lines[0]!.to, 11.5, -2);
  });

  it("joins a 45 degree wire to an unturned turnout's diverging pin in line", () => {
    const { corners } = turning(
      { sw: { kind: "turnout", at: [10, 0] }, p1: bend(12, -1) },
      ["sw.diverging", "p1.P"],
    );
    expect(corners).toEqual([]);
  });

  it("cuts a 45 degree turnout's diverging pin, whose track ends level", () => {
    // diverging at (12, 0.5), level; the wire is 0.71 long, to (12.5, 1).
    const { corners, cuts } = turning(
      {
        sw: { kind: "turnout", at: [10, 0], rot: 45 },
        p1: { kind: "pin", at: [12, 1], rot: 90 },
      },
      ["sw.diverging", "p1.P"],
    );
    expect(cuts.get("sw")?.get("diverging")?.by).toBeCloseTo(STRAIGHT);
    near(cuts.get("sw")?.get("diverging")?.mid, 1.989, 0.5625);
    near(corners[0]!.to, 12.25, 0.75);
  });

  it("leaves a 45 degree turnout's toe alone, its diverging road curving from the pin", () => {
    // toe at (10.5, 0), on the diagonal; the wire goes level.
    const { corners, cuts } = turning(
      {
        sw: { kind: "turnout", at: [10, 0], rot: 45 },
        p1: { kind: "pin", at: [8, 0], rot: 90 },
      },
      ["sw.toe", "p1.P"],
    );
    expect(corners).toEqual([]);
    expect(cuts.size).toBe(0);
  });

  it("keeps a track width of a portal's stub, so the curve begins inside the mouth", () => {
    const { cuts } = turning(
      { out: { kind: "portal", at: [6, 0] }, p1: bend(4, 2) },
      ["out.P", "p1.P"],
    );
    expect(cuts.get("out")?.get("P")?.by).toBeCloseTo(0.69 - 0.15);
  });

  it("curves at both ends of one wire between two symbols, and leaves it no straight part", () => {
    // west.B at (6, 0.5) and east.A at (7, 1.5), both level: the two curves
    // meet at the middle of the wire, (6.5, 1).
    const { corners, lines, cuts } = turning(
      {
        west: { kind: "block", at: [0, 0] },
        east: { kind: "block", at: [7, 1] },
      },
      ["west.B", "east.A"],
    );
    expect(corners).toHaveLength(2);
    near(corners[0]!.to, 6.5, 1);
    near(corners[1]!.from, 7.052, 1.375);
    near(corners[1]!.to, 6.5, 1);
    expect(lines).toEqual([]);
    expect(cuts.get("east")?.get("A")?.by).toBeCloseTo(D);
  });

  it("curves between two symbols where a pin was dropped on a pin out of line", () => {
    // A 45 degree turnout's straight pin and an upright block's A, both at
    // (11.5, 1): the one track comes down the diagonal, the other goes down.
    // Each symbol draws its half, and the wire, having no length, nothing.
    const { corners, lines, cuts } = turning(
      {
        sw: { kind: "turnout", at: [10, 0], rot: 45 },
        up: { kind: "block", at: [11, 1], rot: 90 },
      },
      ["sw.straight", "up.A"],
    );
    expect(corners).toEqual([]);
    expect(lines).toEqual([]);
    expect(cuts.get("sw")?.get("straight")?.by).toBeCloseTo(D);
    near(cuts.get("sw")?.get("straight")?.mid, 1.375, 1.052);
    expect(cuts.get("up")?.get("A")?.by).toBeCloseTo(D);
    near(cuts.get("up")?.get("A")?.mid, 0.052, 0.625);
  });

  it("curves from a symbol onto the wire that leaves a bend sitting on its pin", () => {
    // west.B and the bend are both at (6, 0.5); the wire leaves down at 45.
    const { strokes, cuts } = wiring(
      drawing(
        {
          west: { kind: "block", at: [0, 0] },
          on: bend(6, 0),
          p1: bend(8, 2),
        },
        [
          ["west.B", "on.P"],
          ["on.P", "p1.P"],
        ],
      ),
      UNLIT,
    );
    const { corners, lines } = parts(strokes);
    expect(corners).toHaveLength(1);
    near(corners[0]!.to, 6.5, 1);
    expect(lines).toHaveLength(1);
    near(lines[0]!.from, 6.5, 1);
    expect(cuts.get("west")?.get("B")?.by).toBeCloseTo(D);
    expect(cuts.get("on")?.has("P")).toBe(true);
  });

  it("draws a pin dropped on a pin in line as one point", () => {
    const { corners, lines, cuts } = turning(
      {
        west: { kind: "block", at: [0, 0] },
        east: { kind: "block", at: [6, 0] },
      },
      ["west.B", "east.A"],
    );
    expect(corners).toEqual([]);
    expect(cuts.size).toBe(0);
    expect(lines).toEqual([{ from: { x: 6, y: 0.5 }, to: { x: 6, y: 0.5 } }]);
  });

  it("leaves a pin dropped on a pin sharp where one track is a curve to the pin", () => {
    // An upright block's B and a turnout's diverging pin, both at (11.5, 6),
    // the one track vertical and the other at 45 degrees.
    const { corners, lines, cuts } = turning(
      {
        up: { kind: "block", at: [11, 0], rot: 90 },
        sw: { kind: "turnout", at: [10, 6] },
      },
      ["up.B", "sw.diverging"],
    );
    expect(corners).toEqual([]);
    expect(cuts.size).toBe(0);
    expect(lines).toEqual([{ from: { x: 11.5, y: 6 }, to: { x: 11.5, y: 6 } }]);
  });

  it("lights the wire's half as its wire", () => {
    const { strokes } = wiring(
      drawing(
        { west: { kind: "block", at: [0, 0] }, p1: bend(8, 2) },
        [["west.B", "p1.P"]],
      ),
      new Map([["p1.P west.B", { classes: "lit locked" }]]),
    );
    expect(parts(strokes).corners[0]!.worn).toEqual({ classes: "lit locked" });
  });

  it("moves with a symbol a drag is carrying", () => {
    // The bend is carried two squares down, so the level wire now turns at
    // the block; the block has not moved, and reads the curve where it is.
    const { strokes, cuts } = wiring(
      drawing(
        { west: { kind: "block", at: [0, 0] }, p1: bend(8, 0) },
        [["west.B", "p1.P"]],
      ),
      UNLIT,
      (name) => (name === "p1" ? { x: 0, y: 2 } : { x: 0, y: 0 }),
    );
    expect(parts(strokes).corners).toHaveLength(1);
    expect(cuts.get("west")?.get("B")?.by).toBeCloseTo(D);
    near(cuts.get("west")?.get("B")?.mid, 5.948, 0.625);
  });
});
