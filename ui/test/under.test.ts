/**
 * What a click on the canvas landed on.
 *
 * Grid coordinates throughout: a point here is squares from the origin, which
 * is what the canvas hands over once it has converted the pointer. Nothing in
 * this file needs a DOM.
 */

import { describe, expect, it } from "vitest";

import type { Drawing } from "../src/model/drawing.js";
import type { Review } from "../src/model/store.js";
import { under, within } from "../src/model/under.js";

/** A review that says nothing, which is what a drawing has before the store
 *  has answered for it. */
const NOTHING: Review = {
  red_pins: [],
  junctions: [],
  joints: [],
  layout: null,
  explain: null,
  refused: null,
};

/** One turnout on the square at (2, 1). Its pins are the face centres of that
 *  square: the toe west at (2, 1.5), the straight east at (3, 1.5), the
 *  diverging north at (2.5, 1). The middle of the square is half a square from
 *  each of them, which is well outside the hit radius. */
const ONE_TURNOUT: Drawing = {
  drawing: "under",
  symbols: { sw1: { kind: "turnout", at: [2, 1] } },
  wires: [],
};

/** One bend on the west face of the square at (4, 2), which is the point
 *  (4, 2.5). It occupies no square. */
const ONE_BEND: Drawing = {
  drawing: "under",
  symbols: { n1: { kind: "pin", at: [4, 2], rot: 0 } },
  wires: [],
};

/**
 * Two blocks with a turnout standing between them, wired end to end.
 *
 * A block is six squares long, so `b1` holds 0 to 5 and `b2` holds 8 to 13,
 * leaving square 6 empty and square 7 to the turnout. The wire runs from
 * `b1.B` at (6, 0.5) straight to `b2.A` at (8, 0.5), which takes it across
 * both of those squares: over bare canvas at 6, and over a symbol at 7.
 */
const WIRED: Drawing = {
  drawing: "under",
  symbols: {
    b1: { kind: "block", at: [0, 0], length: 1000 },
    sw1: { kind: "turnout", at: [7, 0] },
    b2: { kind: "block", at: [8, 0], length: 1000 },
  },
  wires: [["b1.B", "b2.A"]],
};

describe("the symbol under a point", () => {
  it("finds the symbol whose square holds the point", () => {
    expect(under(ONE_TURNOUT, NOTHING, { x: 2.5, y: 1.5 }).symbol).toBe("sw1");
  });

  it("finds nothing on an empty square", () => {
    expect(under(ONE_TURNOUT, NOTHING, { x: 7, y: 7 }).symbol).toBeNull();
  });
});

/** A junction is the connected group of non-block symbols, which `/review`
 *  works out. Finding it is a lookup in that answer, never a derivation here. */
describe("the junction a symbol belongs to", () => {
  const reviewed: Review = {
    ...NOTHING,
    junctions: [{ name: "airolo", names: ["airolo"], symbols: ["sw1", "sw2"] }],
  };

  it("names the junction the symbol under the point is part of", () => {
    expect(under(ONE_TURNOUT, reviewed, { x: 2.5, y: 1.5 }).junction?.name).toBe(
      "airolo",
    );
  });

  it("finds no junction where there is no symbol", () => {
    expect(under(ONE_TURNOUT, reviewed, { x: 7, y: 7 }).junction).toBeNull();
  });
});

/** A press near a pin means the pin, not the symbol carrying it: it is where a
 *  wire starts, and the symbol is still named so a right-click there asks about
 *  the turnout (EDITOR.md#editing). */
describe("a pin near a point", () => {
  it("takes the pin, and names the symbol it belongs to", () => {
    const found = under(ONE_TURNOUT, NOTHING, { x: 2.05, y: 1.5 });
    expect(found.pin).toBe("sw1.toe");
    expect(found.symbol).toBe("sw1");
  });

  /** A bend sits on a face and occupies no square at all (EDITOR.md#canvas),
   *  so no cell holds it and its pin is the only thing there is to find. The
   *  symbol has to come from the pin rather than from the square, or a bend
   *  could never be selected, deleted or dragged. */
  it("names a bend, which has no square to be found by", () => {
    const found = under(ONE_BEND, NOTHING, { x: 4, y: 2.5 });
    expect(found.pin).toBe("n1.P");
    expect(found.symbol).toBe("n1");
  });
});

/**
 * A wire has no symbol to select and so no keystroke to take it: the
 * right-click menu is the only way to cut one, which makes finding it the
 * whole of that feature (EDITOR.md#editing).
 */
describe("the wire under a point", () => {
  it("finds the wire crossing bare canvas", () => {
    const found = under(WIRED, NOTHING, { x: 6.5, y: 0.5 });
    expect(found.wire).toEqual(["b1.B", "b2.A"]);
    expect(found.symbol).toBeNull();
  });

  /** A symbol's own wires pass within a hair of its pins, and an abutted one
   *  has no length at all, so a wire is near wherever a symbol is. A click on
   *  a turnout is a question about the turnout. */
  it("offers no wire where a symbol is, though one passes there", () => {
    const found = under(WIRED, NOTHING, { x: 7.5, y: 0.5 });
    expect(found.symbol).toBe("sw1");
    expect(found.wire).toBeNull();
  });
});

/**
 * A joint is the way from one block end to another crossing no connection
 * symbol, which makes it a connection in its own right and gives it a name to
 * offer. It has no symbol to click, only its wires, and `/review` says which
 * wires those are.
 */
describe("the joint under a point", () => {
  const reviewed: Review = {
    ...NOTHING,
    joints: [
      { ends: ["b1.B", "b2.A"], wires: [["b1.B", "b2.A"]], name: null, names: [] },
    ],
  };

  it("finds the joint whose wire passes nearest", () => {
    expect(under(WIRED, reviewed, { x: 6.5, y: 0.5 }).joint?.ends).toEqual([
      "b1.B",
      "b2.A",
    ]);
  });

  it("finds no joint away from any of its wires", () => {
    expect(under(WIRED, reviewed, { x: 3, y: 4 }).joint).toBeNull();
  });
});

/**
 * While a drag is in flight the selection is drawn away from where the
 * document puts it, and a click has to land on what is on screen. The offset
 * arrives as a function of the symbol's name, so this module never learns that
 * a drag exists: it is told where things are drawn and answers accordingly.
 */
describe("a symbol drawn away from where it sits", () => {
  const shifted = (name: string) =>
    name === "sw1" ? { x: 3, y: 0 } : { x: 0, y: 0 };

  it("finds the symbol where it is drawn", () => {
    expect(under(ONE_TURNOUT, NOTHING, { x: 5.5, y: 1.5 }, shifted).symbol).toBe(
      "sw1",
    );
  });

  it("finds nothing where the document still says it sits", () => {
    expect(
      under(ONE_TURNOUT, NOTHING, { x: 2.5, y: 1.5 }, shifted).symbol,
    ).toBeNull();
  });

  it("moves the symbol's pins with it", () => {
    expect(under(ONE_TURNOUT, NOTHING, { x: 5.05, y: 1.5 }, shifted).pin).toBe(
      "sw1.toe",
    );
  });
});

/**
 * The rubber band is the same question over a rectangle instead of a point. A
 * symbol is taken by its centre rather than by any overlap, so dragging a band
 * across the middle of a row takes that row and nothing that merely reaches
 * into it.
 */
describe("the symbols within a band", () => {
  it("takes the symbols whose centres the band covers", () => {
    expect(within(WIRED, { x: 0, y: 0 }, { x: 9, y: 1 }).sort()).toEqual([
      "b1",
      "sw1",
    ]);
  });

  it("reads the band whichever corner it was dragged from", () => {
    expect(within(WIRED, { x: 9, y: 1 }, { x: 0, y: 0 }).sort()).toEqual([
      "b1",
      "sw1",
    ]);
  });
});
